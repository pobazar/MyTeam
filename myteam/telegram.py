"""Transport never includes URLs, tokens or message bodies in exceptions/logs."""
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from django.conf import settings

@dataclass
class DeliveryError(Exception):
    code: str
    retry_after: int = 0
    permanent: bool = False
    uncertain: bool = False

def call(method, payload):
    req = urllib.request.Request('https://api.telegram.org/bot'+settings.TG_BOT_TOKEN+'/'+method, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read(4096))
        except (ValueError, OSError):
            detail = {}
        raise DeliveryError(f'telegram_{error.code}', min(int(detail.get('parameters',{}).get('retry_after',0)),86400), error.code in (400,401,403,404)) from None
    except (OSError, ValueError):
        raise DeliveryError('transport_unknown', uncertain=True) from None
    if not result.get('ok'):
        raise DeliveryError('telegram_rejected')
    return result['result']

def send(chat_id, text, payload=None):
    return call('sendMessage', {'chat_id':chat_id,'text':text,'parse_mode':'HTML','link_preview_options':{'is_disabled':True},**(payload or {})})['message_id']
