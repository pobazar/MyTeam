import json
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from myteam.users import approve_login, confirm_login, digest
from myteam.models import LoginAttempt, Person
class AuthTests(TestCase):
    def test_untrusted_expired_and_repeated_login(self):
        a = LoginAttempt.objects.create(token_hash=digest('ok'),confirmation_code='123456',expires_at=timezone.now()+timedelta(minutes=10))
        self.assertFalse(approve_login('forged',{'id':12},12))
        self.assertFalse(approve_login('ok',{'id':12},13))
        self.assertTrue(approve_login('ok',{'id':12,'username':'old'},12))
        self.assertFalse(approve_login('ok',{'id':12},12))
        LoginAttempt.objects.create(token_hash=digest('new'),confirmation_code='654321',expires_at=timezone.now()+timedelta(minutes=10))
        self.assertTrue(approve_login('new',{'id':12,'username':'new'},12))
        self.assertEqual(Person.objects.count(),1)
        self.assertFalse(Person.objects.get().reachable)
        from myteam.notifications import drain
        from myteam.clock import Clock
        drain(Clock(),lambda *args:123,force=True)
        self.assertTrue(Person.objects.get().reachable)
        LoginAttempt.objects.create(token_hash=digest('expired'),confirmation_code='111111',expires_at=timezone.now()-timedelta(seconds=1))
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
        self.assertNotIn('person_id',self.client.session)
        attempt=LoginAttempt.objects.get(token_hash=digest(token))
        self.assertFalse(confirm_login(attempt.id,{'id':43},43))
        self.assertTrue(confirm_login(attempt.id,{'id':42},42))
        self.client.post('/login/')
        self.assertEqual(Person.objects.get().id.hex,str(self.client.session['person_id']).replace('-',''))

class WebhookTests(TestCase):
    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret',SEND_TELEGRAM=False)
    def test_signed_start_deduplicates_and_acknowledges_delivery(self):
        from unittest.mock import patch
        from myteam.models import Notification
        self.client.get('/login/')
        token=self.client.session['login_token']
        payload={'update_id':42,'message':{'from':{'id':42},'chat':{'type':'private','id':42},'text':'/start l_'+token}}
        with patch('myteam.notifications.send',return_value=7) as send:
            for _ in range(2):
                response=self.client.post('/telegram/webhook/',data=json.dumps(payload),content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret')
                self.assertEqual(response.status_code,200)
        self.assertEqual(send.call_count,1)
        self.assertTrue(Person.objects.get().reachable)
        self.assertEqual(Notification.objects.get().status,'sent')

class ConfirmationTests(TestCase):
    def test_start_is_not_confirmation_and_another_person_cannot_confirm(self):
        self.client.get('/login/')
        token=self.client.session['login_token']
        approve_login(token,{'id':42},42)
        self.assertFalse(self.client.post('/login/status/').json()['authenticated'])
        attempt=LoginAttempt.objects.get(token_hash=digest(token))
        self.assertEqual(len(attempt.confirmation_code),6)
        self.assertFalse(confirm_login(attempt.id,{'id':43},43))
        self.assertTrue(confirm_login(attempt.id,{'id':42},42))
        self.assertTrue(self.client.post('/login/status/').json()['authenticated'])
        self.assertFalse(confirm_login(attempt.id,{'id':42},42))
    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_callback_from_telegram_confirms_bound_browser(self):
        from unittest.mock import patch
        self.client.get('/login/')
        token=self.client.session['login_token']
        approve_login(token,{'id':42},42)
        attempt=LoginAttempt.objects.get(token_hash=digest(token))
        payload={'update_id':100,'callback_query':{'id':'callback','from':{'id':42},'message':{'chat':{'type':'private','id':42}},'data':'login:'+str(attempt.id)}}
        with patch('myteam.telegram.call',return_value=True), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post('/telegram/webhook/',data=json.dumps(payload),content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret').status_code,200)
        self.assertTrue(self.client.post('/login/status/').json()['authenticated'])
