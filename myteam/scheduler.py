"""GitHub OIDC-authenticated scheduler. No shared secret, browser access or clock override."""
import json
import time
import jwt
from django.conf import settings
from django.db.models import Min
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .clock import Clock
from .jobs import tick
from .models import Notification, Round
from .notifications import drain

ISSUER='https://token.actions.githubusercontent.com'
AUDIENCE='https://myteam-web.onrender.com'
WORKFLOW='pobazar/MyTeam/.github/workflows/schedule.yml@refs/heads/main'
KEYS=jwt.PyJWKClient(ISSUER+'/.well-known/jwks',cache_keys=True,lifespan=300,timeout=5)

def verify_token(token):
    if not token or len(token)>20000:raise ValueError('Invalid identity')
    key=KEYS.get_signing_key_from_jwt(token).key
    claims=jwt.decode(token,key,algorithms=['RS256'],audience=AUDIENCE,issuer=ISSUER,
        options={'require':['exp','iat','nbf','iss','aud','repository_id','repository','ref','workflow_ref','event_name']})
    if not (claims['repository_id']=='1431966263' and claims['repository']=='pobazar/MyTeam'
            and claims['ref']=='refs/heads/main' and claims['workflow_ref']==WORKFLOW
            and claims['event_name'] in ('schedule','workflow_dispatch')):
        raise ValueError('Untrusted workflow')
    return claims

@csrf_exempt
@require_POST
def run(request):
    # Auth is independent of cookies and CSRF; token claims must name this exact main workflow.
    if request.headers.get('Origin'):return JsonResponse({'error':'server_only'},status=403)
    try:verify_token(request.headers.get('X-Myteam-Scheduler-Token',''))
    except jwt.PyJWKClientConnectionError:
        return JsonResponse({'error':'identity_provider_unavailable'},status=503)
    except (jwt.PyJWTError,ValueError,TypeError,KeyError):
        return JsonResponse({'error':'invalid_workflow_identity'},status=403)
    if len(request.body)>1024:return JsonResponse({'error':'invalid_request'},status=400)
    try:body=json.loads(request.body)
    except (ValueError,UnicodeDecodeError):return JsonResponse({'error':'invalid_request'},status=400)
    if not isinstance(body,dict) or set(body)!={'mode'} or body['mode'] not in ('verify','run'):
        return JsonResponse({'error':'invalid_request'},status=400)
    if body['mode']=='verify':
        # Real auth + DB check with no tick, outbox changes, participants or messages.
        Round.objects.exists()
        return JsonResponse({'status':'verified','telegram_enabled':settings.SEND_TELEGRAM})
    clock=Clock()
    tick(clock)
    processed=0
    deadline=time.monotonic()+15
    for _ in range(20):
        if time.monotonic()>=deadline:break
        count=drain(clock,limit=1)
        processed+=count
        if not count:break
    # Publication delivery report may become due after draining the participant messages.
    tick(clock)
    pending=Notification.objects.filter(status='pending')
    next_at=pending.aggregate(value=Min('next_attempt_at'))['value']
    delay=max(1,min(60,int((next_at-clock.now()).total_seconds())+1)) if next_at else 0
    # Wait for a crashed in-flight sender's lease before reporting the outbox complete.
    sending=Notification.objects.filter(status='sending').count()
    if sending:delay=delay or 30
    errors=Round.objects.exclude(state__in=['completed','expired']).exclude(preparation_error='').count()
    if pending.exists() and not settings.SEND_TELEGRAM:
        return JsonResponse({'error':'telegram_delivery_disabled'},status=503)
    return JsonResponse({'status':'retry' if errors else 'ok','processed':processed,
        'pending':pending.count()+sending,'retry_after':delay,'stage_errors':errors})
