import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import SimpleTestCase
class ExternalMonitorTests(SimpleTestCase):
    def test_total_application_outage_uses_independent_persistent_state(self):
        spec=importlib.util.spec_from_file_location('external_monitor',Path(__file__).parents[1]/'scripts/external_monitor.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with TemporaryDirectory() as directory:
            state=Path(directory)/'state.json'
            def restore():return json.loads(state.read_text()) if state.exists() else {}
            with patch.object(module,'STATE',state),patch.object(module,'restore',side_effect=restore),patch.object(module,'send',return_value=True) as send,patch.dict('os.environ',{'PUBLIC_URL':'https://isolated.invalid','OPS_SECRET':'test'}):
                with patch.object(module,'request',side_effect=ConnectionError('application and DB unavailable')):
                    module.main();module.main();module.main()
                self.assertEqual(send.call_count,1)
                with patch.object(module,'request',return_value=b'{"status":"ok"}'):
                    module.main();module.main()
                self.assertEqual(send.call_count,2)
                self.assertFalse(json.loads(state.read_text())['open'])
