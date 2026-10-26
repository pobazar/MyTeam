from django.test import TestCase,Client,override_settings
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from myteam.models import Person,Achievement
from myteam.profiles import team_identity

@override_settings(FRONTEND_ORIGINS=['https://pobazar.github.io'])
class RequestPerformanceTests(TestCase):
    def setUp(self):
        group,confidence=team_identity('Дизайн')
        self.person=Person.objects.create(telegram_id=77,chat_id=77,delivery_verified_at=timezone.now(),full_name='Анна',team='Дизайн',team_group=group,team_confidence=confidence,city='Москва',city_key='moskva',onboarding_done=True)
        self.session=SessionStore();self.session['person_id']=str(self.person.id);self.session.create()
        self.headers={'HTTP_ORIGIN':'https://pobazar.github.io','HTTP_AUTHORIZATION':'Bearer '+self.session.session_key}
        self.client=Client();self.client.get('/profile/',**self.headers);self.client.cookies.clear()
    def test_profile_and_history_load_session_once(self):
        Achievement.objects.create(person=self.person,key='first_coffee')
        # A newly earned badge appears without a stale cache or an extra SQL read.
        # Profile joins the badge test into the person query; history has one data query.
        # Pages API adds one UPDATE to extend idle expiry, without rereading the session.
        for path,count in (('/profile/',2),('/history/',3),('/api/profile/',3)):
            with self.subTest(path=path),self.assertNumQueries(count):
                response=self.client.get(path,**self.headers)
                self.assertEqual(response.status_code,200)
            if path=='/profile/':self.assertContains(response,'<p class="badge">Первый кофе</p>',html=True)
            if path=='/api/profile/':self.assertIsNotNone(response.json()['achievements'][0]['earned_at'])
            self.client.cookies.clear()
        self.assertIn('app;dur=',response['Server-Timing'])
        self.assertEqual(response['Timing-Allow-Origin'],'https://pobazar.github.io')
    def test_name_edit_does_not_rescan_teams_or_start_extra_transaction(self):
        with self.assertNumQueries(3):
            response=self.client.post('/profile/',{'full_name':'Анна Соколова','team':'Дизайн','city':'Москва'},**self.headers)
        self.assertEqual(response.status_code,200)
        self.person.refresh_from_db();self.assertEqual(self.person.full_name,'Анна Соколова')
    def test_expired_bearer_is_rejected_even_if_the_database_row_still_exists(self):
        from django.contrib.sessions.models import Session
        Session.objects.filter(session_key=self.session.session_key).update(expire_date=timezone.now())
        response=self.client.get('/history/',**self.headers)
        self.assertEqual(response.status_code,401)
    def test_active_dashboard_reads_both_weeks_and_registration_flags_together(self):
        from datetime import datetime,timedelta
        from unittest.mock import patch
        from myteam.clock import MOSCOW,FrozenClock
        from myteam.rounds import ensure_round
        from myteam.jobs import tick
        from myteam.models import Enrollment
        now=datetime(2026,10,28,10,tzinfo=MOSCOW)
        r=ensure_round(now.replace(hour=9))
        other=Person.objects.create(telegram_id=78,full_name='Михаил',team='Разработка',city='Москва',city_key='moskva')
        for person in (self.person,other):Enrollment.objects.create(person=person,round=r)
        tick(FrozenClock(r.prepares_at));tick(FrozenClock(r.starts_at))
        upcoming=ensure_round(r.ends_at)
        Enrollment.objects.create(person=self.person,round=upcoming)
        with patch('myteam.clock.Clock.now',return_value=now),self.assertNumQueries(5):
            response=self.client.get('/',**self.headers)
        self.assertContains(response,'Поделиться результатом')
        self.assertContains(response,'Ты записан на следующую неделю.')
