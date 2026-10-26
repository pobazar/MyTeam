from datetime import timedelta
from unittest.mock import patch
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import Client,TestCase,override_settings
from django.utils import timezone
from myteam.models import Person


@override_settings(FRONTEND_ORIGINS=['https://pobazar.github.io'])
class SlidingSessionTests(TestCase):
    def setUp(self):
        self.person=Person.objects.create(telegram_id=812,full_name='Анна',team='Дизайн',city='Москва',city_key='moskva',onboarding_done=True)
        self.session=SessionStore()
        self.session['person_id']=str(self.person.id)
        self.session.create()
        self.key=self.session.session_key
        self.headers={'HTTP_ORIGIN':'https://pobazar.github.io','HTTP_AUTHORIZATION':'Bearer '+self.key}
        self.client=Client()
        # Seed CSRF exactly as an authenticated browser before measuring renewals.
        self.client.get('/api/profile/',**self.headers)
        self.client.cookies.clear()

    def test_activity_extends_existing_session_without_changing_key_or_payload(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE,30*86400)
        before=Session.objects.get(pk=self.key).session_data
        now=timezone.now()
        Session.objects.filter(pk=self.key).update(expire_date=now+timedelta(minutes=1))
        with patch('django.utils.timezone.now',return_value=now):
            self.assertEqual(self.client.get('/api/profile/',**self.headers).status_code,200)
        row=Session.objects.get(pk=self.key)
        self.assertEqual(row.expire_date,now+timedelta(days=30))
        self.assertEqual(row.session_data,before)
        # Another visit 29 days later slides the deadline out again.
        later=now+timedelta(days=29)
        with patch('django.utils.timezone.now',return_value=later):
            self.assertEqual(self.client.get('/api/history/',**self.headers).status_code,200)
        self.assertEqual(Session.objects.get(pk=self.key).expire_date,later+timedelta(days=30))

    def test_thirty_days_without_activity_requires_new_login(self):
        deadline=Session.objects.get(pk=self.key).expire_date
        with patch('django.utils.timezone.now',return_value=deadline):
            self.assertEqual(self.client.get('/api/profile/',**self.headers).status_code,401)
        self.assertEqual(Session.objects.get(pk=self.key).expire_date,deadline)

    def test_anonymous_and_health_requests_do_not_extend_account(self):
        expiry=timezone.now()+timedelta(days=1)
        Session.objects.filter(pk=self.key).update(expire_date=expiry)
        self.assertEqual(self.client.get('/health/ready',**self.headers).status_code,200)
        self.client.get('/api/profile/',HTTP_ORIGIN='https://pobazar.github.io')
        self.assertEqual(Session.objects.get(pk=self.key).expire_date,expiry)
        anonymous=SessionStore();anonymous.create()
        self.client.get('/api/profile/',HTTP_AUTHORIZATION='Bearer '+anonymous.session_key)
        self.assertEqual(Session.objects.get(pk=self.key).expire_date,expiry)

    def test_logout_and_concurrent_logout_never_recreate_session(self):
        from myteam.pages import PagesSessionMiddleware
        from django.http import JsonResponse
        from django.test import RequestFactory
        request=RequestFactory().get('/api/profile/',**self.headers)
        session=SessionStore(self.key);session.get('person_id');request.session=session
        def delete_during_request(request):
            Session.objects.filter(pk=self.key).delete()
            return JsonResponse({'state':'authenticated'})
        self.assertEqual(PagesSessionMiddleware(delete_during_request)(request).status_code,200)
        self.assertFalse(Session.objects.filter(pk=self.key).exists())
        self.assertEqual(self.client.get('/api/profile/',**self.headers).status_code,401)

    def test_late_response_cannot_shorten_expiry_set_by_another_request(self):
        expiry=timezone.now()+timedelta(days=31)
        Session.objects.filter(pk=self.key).update(expire_date=expiry)
        self.assertEqual(self.client.get('/api/profile/',**self.headers).status_code,200)
        self.assertEqual(Session.objects.get(pk=self.key).expire_date,expiry)

    def test_rejected_or_failed_requests_do_not_renew(self):
        from myteam.pages import PagesSessionMiddleware
        from django.http import JsonResponse
        from django.test import RequestFactory
        expiry=timezone.now()+timedelta(days=1)
        Session.objects.filter(pk=self.key).update(expire_date=expiry)
        for status in (401,403,404,405,500,503):
            with self.subTest(status=status):
                request=RequestFactory().get('/api/profile/',**self.headers)
                session=SessionStore(self.key);session.get('person_id');request.session=session
                response=PagesSessionMiddleware(lambda request:JsonResponse({'error':'test'},status=status))(request)
                self.assertEqual(response.status_code,status)
                self.assertEqual(Session.objects.get(pk=self.key).expire_date,expiry)
