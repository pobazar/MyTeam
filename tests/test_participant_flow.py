from datetime import datetime,timedelta
from unittest.mock import patch
from django.test import TestCase
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Person,Enrollment,Member,Feedback,Achievement
from myteam.rounds import ensure_round
from myteam.jobs import tick
from myteam.feedback import FeedbackForm,save_feedback
from myteam.profiles import ProfileForm

class ParticipantFlowTests(TestCase):
    def setUp(self):
        self.now=datetime(2026,10,28,10,tzinfo=MOSCOW)
        self.p=Person.objects.create(telegram_id=1,first_name='Анна',last_name='Соколова',chat_id=1,delivery_verified_at=self.now,created_at=self.now)
        session=self.client.session;session['person_id']=str(self.p.id);session.save()
    def complete(self):
        self.p.onboarding_done=True;self.p.full_name='Анна';self.p.team='Дизайн';self.p.city='Москва';self.p.city_key='moskva';self.p.save()
    def published(self):
        self.complete()
        r=ensure_round(self.now.replace(hour=9))
        p=Person.objects.create(telegram_id=2,full_name='Михаил Орлов',team='Разработка',city='Казань',city_key='kazan',onboarding_done=True)
        for person in (self.p,p):Enrollment.objects.create(person=person,round=r)
        tick(FrozenClock(r.prepares_at));tick(FrozenClock(r.starts_at))
        return r,Member.objects.get(round=r,person=self.p)
    def test_onboarding_cannot_be_skipped_and_gates_all_member_routes(self):
        for url in ('/','/profile/','/history/'):
            self.assertRedirects(self.client.get(url),'/onboarding/',fetch_redirect_response=False)
        response=self.client.get('/onboarding/')
        self.assertNotContains(response,'Основная навигация')
        self.assertNotContains(response,'Пропустить')
        self.client.post('/onboarding/',{'action':'skip'})
        self.p.refresh_from_db();self.assertFalse(self.p.onboarding_done)
        self.client.post('/onboarding/');self.client.post('/onboarding/')
        self.p.refresh_from_db();self.assertTrue(self.p.onboarding_done)
        for url in ('/','/history/'):
            self.assertRedirects(self.client.get(url),'/profile/',fetch_redirect_response=False)
        response=self.client.get('/profile/')
        self.assertContains(response,'Как вас зовут')
        self.assertNotContains(response,'Основная навигация')
        self.assertNotContains(response,'Достижения')
        self.assertNotContains(response,'Бот подключён')
        self.assertRedirects(self.client.post('/profile/',{'full_name':'Анна','team':'Дизайн','city':'Москва'}),'/',fetch_redirect_response=False)
        self.p.refresh_from_db();self.assertTrue(self.p.complete)
        response=self.client.get('/profile/')
        self.assertContains(response,'Основная навигация');self.assertContains(response,'Достижения');self.assertContains(response,'Выйти')
        self.assertNotContains(response,'Бот подключён')
    def test_profile_edit_preserves_legacy_names_and_failed_post_does_not_hide_navigation(self):
        self.complete()
        form=ProfileForm({'full_name':'Анна Мария Соколова','team':'Дизайн','city':'Москва'},instance=self.p)
        self.assertTrue(form.is_valid());form.save();self.p.refresh_from_db()
        self.assertEqual(self.p.display_name,'Анна Мария Соколова');self.assertEqual(self.p.last_name,'Соколова')
        response=self.client.post('/profile/',{'full_name':'Анна','team':'','city':'Москва'})
        self.assertContains(response,'Основная навигация')
        self.p.refresh_from_db();self.assertEqual(self.p.team,'Дизайн')
    def test_dashboard_two_weeks_instructions_and_finished_state(self):
        r,m=self.published()
        with patch('myteam.clock.Clock.now',return_value=self.now):
            response=self.client.get('/')
            self.assertContains(response,'Текущая неделя');self.assertContains(response,'Следующая неделя')
            self.assertContains(response,'Что делать на этой неделе');self.assertContains(response,'Поделиться результатом')
            self.assertContains(response,'Михаил Орлов');self.assertContains(response,'Записаться')
            response=self.client.post(f'/meetings/{m.meeting_id}/feedback/',{'outcome':'yes','rating':'4','comment':''})
            self.assertRedirects(response,'/',fetch_redirect_response=False)
            response=self.client.get('/')
            self.assertContains(response,'Спасибо за участие!');self.assertContains(response,'★★★★☆')
            self.assertNotContains(response,'Поделиться результатом');self.assertNotContains(response,'Что делать на этой неделе')
        self.assertEqual(Achievement.objects.filter(person=self.p).count(),1)
        self.assertFalse(Enrollment.objects.exclude(round=r).exists())
    def test_new_member_and_skipped_week_are_different(self):
        self.complete()
        with patch('myteam.clock.Clock.now',return_value=self.now):
            self.assertContains(self.client.get('/'),'Добро пожаловать!')
            self.p.created_at=self.now-timedelta(days=10);self.p.save()
            self.assertContains(self.client.get('/'),'Эту неделю ты пропускаешь')
            self.assertContains(self.client.get('/history/'),'Пропущенные недели в историю не попадают')
    def test_history_rating_entry_then_stars_without_meeting_link(self):
        r,m=self.published()
        with patch('myteam.clock.Clock.now',return_value=r.ends_at):
            response=self.client.get('/history/')
            self.assertContains(response,'Оценить активность');self.assertNotContains(response,'Посмотреть встречу')
            response=self.client.post(f'/meetings/{m.meeting_id}/feedback/',{'outcome':'yes','rating':5,'return_to':'history'})
            self.assertRedirects(response,'/history/',fetch_redirect_response=False)
            response=self.client.get('/history/')
            self.assertContains(response,'★★★★★');self.assertNotContains(response,'Оценить активность')
    def test_no_result_requires_reason_and_history_shows_failure(self):
        r,m=self.published()
        self.assertFalse(FeedbackForm({'outcome':'no'}).is_valid())
        self.assertFalse(FeedbackForm({'outcome':'yes','rating':6}).is_valid())
        self.assertFalse(FeedbackForm({'outcome':'pending'}).is_valid())
        save_feedback(self.p.id,m.meeting_id,{'outcome':'no','comment':'Не совпало время'},FrozenClock(self.now))
        self.assertFalse(Achievement.objects.filter(person=self.p).exists())
        with patch('myteam.clock.Clock.now',return_value=r.ends_at):
            response=self.client.get('/history/')
            self.assertContains(response,'Не получилось провести активность.');self.assertNotContains(response,'Оценить активность')
    def test_legacy_response_keeps_finality_without_inventing_stars(self):
        r,m=self.published()
        answer=Feedback.objects.create(member=m,outcome='yes',impression='positive',again='yes',comment='Старый ответ')
        self.assertTrue(answer.final);self.assertEqual(answer.stars,'')
        with patch('myteam.clock.Clock.now',return_value=r.ends_at):
            response=self.client.get('/history/')
            self.assertContains(response,'Активность проведена. Ответ сохранён.');self.assertNotContains(response,'Оценить активность')
    def test_unrated_old_week_can_be_rated_from_history(self):
        r,m=self.published()
        with patch('myteam.clock.Clock.now',return_value=r.ends_at+timedelta(days=7)):
            response=self.client.get('/history/')
            self.assertContains(response,'Оценить активность')
            response=self.client.post(f'/meetings/{m.meeting_id}/feedback/',{'outcome':'yes','rating':3,'return_to':'history'})
            self.assertRedirects(response,'/history/',fetch_redirect_response=False)
            self.assertEqual(Feedback.objects.get(member=m).rating,3)
    def test_expired_registered_week_is_not_presented_as_still_preparing(self):
        self.complete()
        r=ensure_round(self.now.replace(hour=9));r.state='expired';r.save()
        Enrollment.objects.create(person=self.p,round=r)
        with patch('myteam.clock.Clock.now',return_value=self.now):
            response=self.client.get('/')
            self.assertContains(response,'Активность не состоялась')
            self.assertNotContains(response,'Готовим состав и инструкции')
