import json
import time
from types import SimpleNamespace
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase,Client,override_settings
from myteam import scheduler
from myteam.models import Notification

class SchedulerTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def token(self,**changes):
        now=int(time.time())
        claims=dict(iss=scheduler.ISSUER,aud=scheduler.AUDIENCE,exp=now+300,iat=now,nbf=now-1,
            repository_id='1431966263',repository='pobazar/MyTeam',ref='refs/heads/main',
            workflow_ref=scheduler.WORKFLOW,event_name='workflow_dispatch')
        claims.update(changes)
        return jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'isolated'})
    def call(self,token=None,mode='verify',**headers):
        return Client(enforce_csrf_checks=True).post('/internal/schedule/',json.dumps({'mode':mode}),content_type='application/json',HTTP_X_MYTEAM_SCHEDULER_TOKEN=token or self.token(),**headers)
    def test_real_rsa_identity_verify_is_non_mutating(self):
        with patch.object(scheduler.KEYS,'get_signing_key_from_jwt',return_value=SimpleNamespace(key=self.key.public_key())),patch.object(scheduler,'tick') as tick,patch.object(scheduler,'drain') as drain:
            response=self.call()
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['status'],'verified')
            tick.assert_not_called();drain.assert_not_called()
    def test_untrusted_claims_expiry_signature_and_browser_are_rejected(self):
        with patch.object(scheduler.KEYS,'get_signing_key_from_jwt',return_value=SimpleNamespace(key=self.key.public_key())),patch.object(scheduler,'tick') as tick:
            for change in ({'repository_id':'1'},{'repository':'attacker/MyTeam'},{'ref':'refs/heads/feature'},{'workflow_ref':scheduler.WORKFLOW.replace('schedule.yml','other.yml')},{'event_name':'pull_request'},{'aud':'wrong'},{'iss':'wrong'},{'exp':int(time.time())-1}):
                with self.subTest(change=change):self.assertEqual(self.call(self.token(**change)).status_code,403)
            wrong=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            token=jwt.encode(jwt.decode(self.token(),options={'verify_signature':False}),wrong,algorithm='RS256')
            self.assertEqual(self.call(token).status_code,403)
            self.assertEqual(self.call(HTTP_ORIGIN='https://pobazar.github.io').status_code,403)
            self.assertEqual(self.call('garbage').status_code,403)
            tick.assert_not_called()
    @override_settings(SEND_TELEGRAM=True)
    def test_run_drains_bounded_batches_and_reports_remaining_work(self):
        from django.utils import timezone
        Notification.objects.create(key='isolated',kind='test',chat_id=1,text='test',next_attempt_at=timezone.now())
        with patch.object(scheduler.KEYS,'get_signing_key_from_jwt',return_value=SimpleNamespace(key=self.key.public_key())),patch.object(scheduler,'tick') as tick,patch.object(scheduler,'drain',return_value=0) as drain:
            response=self.call(mode='run');self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['pending'],1)
            self.assertEqual(tick.call_count,2)
            drain.assert_called_once()
    def test_unknown_mode_or_clock_override_is_not_accepted(self):
        with patch.object(scheduler.KEYS,'get_signing_key_from_jwt',return_value=SimpleNamespace(key=self.key.public_key())):
            self.assertEqual(self.call(mode='anything').status_code,400)
            response=self.client.post('/internal/schedule/',json.dumps({'mode':'run','now':'2026-10-28T09:00:00+03:00'}),content_type='application/json',HTTP_X_MYTEAM_SCHEDULER_TOKEN=self.token())
            self.assertEqual(response.status_code,400)
    def test_identity_provider_outage_is_retryable_without_running_work(self):
        with patch.object(scheduler.KEYS,'get_signing_key_from_jwt',side_effect=jwt.PyJWKClientConnectionError('isolated')),patch.object(scheduler,'tick') as tick:
            self.assertEqual(self.call().status_code,503)
            tick.assert_not_called()
