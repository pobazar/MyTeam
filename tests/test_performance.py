from django.test import TestCase,Client,override_settings
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from myteam.models import Person
from myteam.profiles import team_identity

@override_settings(FRONTEND_ORIGINS=['https://pobazar.github.io'])
class RequestPerformanceTests(TestCase):
    def setUp(self):
        group,confidence=team_identity('Дизайн')
        self.person=Person.objects.create(telegram_id=77,full_name='Анна',team='Дизайн',team_group=group,team_confidence=confidence,city='Москва',city_key='moskva',onboarding_done=True)
        self.session=SessionStore();self.session['person_id']=str(self.person.id);self.session.create()
        self.headers={'HTTP_ORIGIN':'https://pobazar.github.io','HTTP_AUTHORIZATION':'Bearer '+self.session.session_key}
        self.client=Client();self.client.get('/profile/',**self.headers);self.client.cookies.clear()
    def test_profile_and_history_load_session_once(self):
        # One session read + one person read + one screen query, no preliminary exists().
        for path in ('/profile/','/history/'):
            with self.subTest(path=path),self.assertNumQueries(3):
                response=self.client.get(path,**self.headers)
                self.assertEqual(response.status_code,200)
            self.client.cookies.clear()
        self.assertIn('app;dur=',response['Server-Timing'])
        self.assertEqual(response['Timing-Allow-Origin'],'https://pobazar.github.io')
    def test_name_edit_does_not_rescan_teams_or_start_extra_transaction(self):
        with self.assertNumQueries(4):
            response=self.client.post('/profile/',{'full_name':'Анна Соколова','team':'Дизайн','city':'Москва'},**self.headers)
        self.assertEqual(response.status_code,200)
        self.person.refresh_from_db();self.assertEqual(self.person.full_name,'Анна Соколова')
    def test_expired_bearer_is_rejected_even_if_the_database_row_still_exists(self):
        from django.contrib.sessions.models import Session
        Session.objects.filter(session_key=self.session.session_key).update(expire_date=timezone.now())
        response=self.client.get('/history/',**self.headers)
        self.assertEqual(response.status_code,401)
