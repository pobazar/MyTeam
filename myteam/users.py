import hashlib
import secrets
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from .models import Person, LoginAttempt

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request.person = Person.objects.filter(pk=request.session.get('person_id')).first() if request.session.get('person_id') else None
        if not request.person:
            return redirect('/login/')
        return view(request, *args, **kwargs)
    return wrapped

def begin_login(request):
    token = request.session.get('login_token')
    if token and LoginAttempt.objects.filter(token_hash=digest(token), expires_at__gt=timezone.now(), consumed_at__isnull=True).exists():
        return token
    token = secrets.token_urlsafe(24)
    LoginAttempt.objects.create(token_hash=digest(token), expires_at=timezone.now()+timedelta(minutes=10))
    request.session['login_token'] = token
    return token

@transaction.atomic
def approve_login(token, sender, chat_id, now=None):
    now = now or timezone.now()
    attempt = LoginAttempt.objects.select_for_update().filter(token_hash=digest(token), expires_at__gt=now, consumed_at__isnull=True, person__isnull=True).first()
    if not attempt or sender.get('is_bot') or sender.get('id') != chat_id:
        return False
    person, _ = Person.objects.get_or_create(telegram_id=sender['id'], defaults={'first_name': sender.get('first_name','')[:100], 'last_name': sender.get('last_name','')[:100]})
    person.username = sender.get('username', '')[:100]
    person.chat_id = chat_id
    # A /start establishes the private chat; an acknowledged outbound message verifies delivery.
    if person.delivery_blocked:person.delivery_verified_at = None
    person.delivery_blocked = False
    person.save()
    from .notifications import enqueue
    enqueue(f'bot-connected:{attempt.id}','bot_connected',chat_id,'МАЙТИМ подключён. Вернитесь в браузер и нажмите «Я нажал Старт — продолжить».',person=person,now=now)
    attempt.person = person
    attempt.save(update_fields=['person'])
    return True

@transaction.atomic
def consume_login(request):
    token = request.session.get('login_token')
    if not token:
        return False
    attempt = LoginAttempt.objects.select_for_update().filter(token_hash=digest(token), expires_at__gt=timezone.now(), consumed_at__isnull=True, person__isnull=False).first()
    if not attempt:
        return False
    attempt.consumed_at = timezone.now()
    attempt.save(update_fields=['consumed_at'])
    request.session.cycle_key()
    request.session['person_id'] = str(attempt.person_id)
    del request.session['login_token']
    return True
