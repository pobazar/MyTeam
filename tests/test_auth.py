import json
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from myteam.users import approve_login, digest
from myteam.models import LoginAttempt, Person
class AuthTests(TestCase):
    def test_untrusted_expired_and_repeated_login(self):
        a = LoginAttempt.objects.create(token_hash=digest('ok'),expires_at=timezone.now()+timedelta(minutes=10))
        self.assertFalse(approve_login('forged',{'id':12},12))
        self.assertFalse(approve_login('ok',{'id':12},13))
        self.assertTrue(approve_login('ok',{'id':12,'username':'old'},12))
        self.assertFalse(approve_login('ok',{'id':12},12))
        LoginAttempt.objects.create(token_hash=digest('new'),expires_at=timezone.now()+timedelta(minutes=10))
        self.assertTrue(approve_login('new',{'id':12,'username':'new'},12))
        self.assertEqual(Person.objects.count(),1)
        self.assertFalse(Person.objects.get().reachable)
        from myteam.notifications import drain
        from myteam.clock import Clock
        drain(Clock(),lambda *args:123,force=True)
        self.assertTrue(Person.objects.get().reachable)
        LoginAttempt.objects.create(token_hash=digest('expired'),expires_at=timezone.now()-timedelta(seconds=1))
        self.assertFalse(approve_login('expired',{'id':13},13))
    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_webhook_rejects_unsigned_data(self):
        self.assertEqual(self.client.post('/telegram/webhook/',data=json.dumps({'update_id':1}),content_type='application/json').status_code,403)
    def test_login_bound_to_browser(self):
        self.client.get('/login/')
        token = self.client.session['login_token']
        approve_login(token,{'id':42},42)
        other = self.client_class()
        other.post('/login/')
        self.assertNotIn('person_id',other.session)
        self.client.post('/login/')
        self.assertEqual(Person.objects.get().id.hex,str(self.client.session['person_id']).replace('-',''))
