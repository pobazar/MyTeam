import importlib.util
from pathlib import Path
from unittest.mock import patch
import urllib.error
from django.test import SimpleTestCase

class ScheduleRunnerTests(SimpleTestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('schedule_runner',Path(__file__).parents[1]/'scripts/run_schedule.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    def test_temporary_outage_recovers_and_verify_never_requests_run(self):
        m=self.load();calls=[]
        def request(url,headers=None,data=None,timeout=45):
            calls.append((url,data))
            if len(calls)==1:raise OSError()
            return {'status':'verified'} if url==m.ENDPOINT else {'status':'ok'}
        with patch.object(m,'request',side_effect=request),patch.object(m,'identity',return_value='isolated'),patch.object(m.time,'sleep'),patch.dict('os.environ',{'MYTEAM_VERIFY_ONLY':'true'}):
            self.assertEqual(m.main(),0)
        self.assertEqual(__import__('json').loads(calls[-1][1]),{'mode':'verify'})
    def test_run_continues_pending_batches_and_gets_fresh_identity(self):
        m=self.load()
        with patch.object(m,'request',side_effect=[{}, {'status':'ok','pending':1,'retry_after':1}, {}, {'status':'ok','pending':0}]),patch.object(m,'identity',return_value='isolated') as identity,patch.object(m.time,'sleep'),patch.dict('os.environ',{'MYTEAM_VERIFY_ONLY':'false'}):
            self.assertEqual(m.main(),0)
            self.assertEqual(identity.call_count,2)
    def test_invalid_identity_is_not_retried_or_treated_as_success(self):
        m=self.load()
        with patch.object(m,'request',side_effect=urllib.error.HTTPError(m.ENDPOINT,403,'forbidden',None,None)),patch.object(m.time,'sleep') as sleep:
            self.assertEqual(m.main(),1);sleep.assert_not_called()
