import re
from django.test import TestCase,Client,override_settings
from django.contrib.sessions.backends.db import SessionStore
from myteam.models import LoginAttempt
from myteam.users import approve_login,confirm_login,digest

@override_settings(TELEGRAM_BOT_USERNAME='isolated_bot',FRONTEND_ORIGINS=['https://pobazar.github.io'],CSRF_TRUSTED_ORIGINS=['https://pobazar.github.io'])
class PagesTests(TestCase):
    origin='https://pobazar.github.io'
    def test_cross_origin_session_without_cookies_and_explicit_confirmation(self):
        client=Client(enforce_csrf_checks=True)
        session=client.get('/bridge/bootstrap/',HTTP_ORIGIN=self.origin).json()['session']
        client.cookies.clear()
        response=client.get('/login/',HTTP_ORIGIN=self.origin,HTTP_AUTHORIZATION='Bearer '+session)
        csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',response.content.decode()).group(1)
        token=SessionStore(session)['login_token']
        approve_login(token,{'id':42},42)
        client.cookies.clear()
        response=client.post('/login/status/',{'csrfmiddlewaretoken':csrf},HTTP_ORIGIN=self.origin,HTTP_AUTHORIZATION='Bearer '+session)
        self.assertFalse(response.json()['authenticated'])
        attempt=LoginAttempt.objects.get(token_hash=digest(token))
        self.assertTrue(confirm_login(attempt.id,{'id':42},42))
        client.cookies.clear()
        response=client.post('/login/status/',{'csrfmiddlewaretoken':csrf},HTTP_ORIGIN=self.origin,HTTP_AUTHORIZATION='Bearer '+session)
        self.assertTrue(response.json()['authenticated'])
        fresh=response['X-Myteam-Session'];self.assertNotEqual(session,fresh)
        client.cookies.clear()
        self.assertEqual(client.get('/profile/',HTTP_ORIGIN=self.origin,HTTP_AUTHORIZATION='Bearer '+fresh).status_code,200)
        self.assertEqual(client.get('/profile/',HTTP_ORIGIN=self.origin,HTTP_AUTHORIZATION='Bearer '+session).status_code,401)
    def test_cors_and_csrf_are_not_opened_to_other_sites(self):
        self.assertEqual(self.client.get('/bridge/bootstrap/',HTTP_ORIGIN='https://untrusted.invalid').status_code,403)
        response=self.client.options('/login/status/',HTTP_ORIGIN=self.origin,HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertEqual(response.status_code,204)
        self.assertEqual(response['Access-Control-Allow-Origin'],self.origin)
        self.assertNotIn('Access-Control-Allow-Credentials',response)
        self.assertEqual(self.client.options('/login/status/',HTTP_ORIGIN='https://untrusted.invalid',HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST').status_code,403)
