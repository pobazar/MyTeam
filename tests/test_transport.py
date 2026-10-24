import io,json,urllib.error
from unittest.mock import patch
from django.test import SimpleTestCase,override_settings
from myteam.telegram import call,DeliveryError
class TransportTests(SimpleTestCase):
    @override_settings(TG_BOT_TOKEN='isolated-test-token')
    def test_http_error_is_sanitized_and_retry_after_preserved(self):
        error=urllib.error.HTTPError('https://api.telegram.org/botSECRET/sendMessage',429,'sensitive',{},io.BytesIO(json.dumps({'parameters':{'retry_after':123}}).encode()))
        with patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaises(DeliveryError) as caught:call('sendMessage',{'text':'private message'})
        self.assertEqual(caught.exception.retry_after,123)
        self.assertNotIn('SECRET',str(caught.exception))
        self.assertNotIn('private message',str(caught.exception))
    def test_lost_response_is_uncertain(self):
        with patch('urllib.request.urlopen',side_effect=TimeoutError()):
            with self.assertRaises(DeliveryError) as caught:call('sendMessage',{})
        self.assertTrue(caught.exception.uncertain)
