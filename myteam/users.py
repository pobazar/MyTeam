import hashlib
import secrets
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from .models import Person, LoginAttempt

def private_actor(sender,chat_id):
    value=sender.get('id')
    return isinstance(value,int) and not isinstance(value,bool) and value>0 and value==chat_id and not sender.get('is_bot')

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request.person = Person.objects.filter(pk=request.session.get('person_id')).first() if request.session.get('person_id') else None
        if not request.person:
            return redirect('/login/')
        if not request.person.onboarding_done and view.__name__!='onboarding':return redirect('/onboarding/')
        if request.person.onboarding_done and not request.person.complete and view.__name__ not in ('onboarding','profile'):return redirect('/profile/')
        return view(request, *args, **kwargs)
    return wrapped

def begin_login(request):
    token = request.session.get('login_token')
    if token and LoginAttempt.objects.filter(token_hash=digest(token), expires_at__gt=timezone.now(), consumed_at__isnull=True,confirmation_code__gt='').exists():
        return token
    token = secrets.token_urlsafe(24)
    LoginAttempt.objects.create(token_hash=digest(token), confirmation_code=f'{secrets.randbelow(1000000):06d}', expires_at=timezone.now()+timedelta(minutes=10))
    request.session['login_token'] = token
    return token

@transaction.atomic
def approve_login(token, sender, chat_id, now=None):
    now = now or timezone.now()
    attempt = LoginAttempt.objects.select_for_update().filter(token_hash=digest(token), expires_at__gt=now, consumed_at__isnull=True, person__isnull=True,confirmation_code__gt='').first()
    if not attempt or not private_actor(sender,chat_id):
        return False
    person, _ = Person.objects.get_or_create(telegram_id=sender['id'], defaults={'first_name': sender.get('first_name','')[:100], 'last_name': sender.get('last_name','')[:100]})
    person.username = sender.get('username', '')[:100]
    person.chat_id = chat_id
    # A /start establishes the private chat; an acknowledged outbound message verifies delivery.
    if person.delivery_blocked:person.delivery_verified_at = None
    person.delivery_blocked = False
    person.save()
    from .notifications import enqueue
    enqueue(f'bot-login:{attempt.id}','bot_login',chat_id,f'Вход в МАЙТИМ. Код: {attempt.confirmation_code}\nСравните код с кодом на странице входа. Подтверждайте только вход, который начали сами.',person=person,now=now,payload={'reply_markup':{'inline_keyboard':[[{'text':'Подтвердить вход','callback_data':f'login:{attempt.id}'}]]}})
    attempt.person = person
    attempt.save(update_fields=['person'])
    return True

@transaction.atomic
def consume_login(request):
    token = request.session.get('login_token')
    if not token:
        return False
    attempt = LoginAttempt.objects.select_for_update().filter(token_hash=digest(token), expires_at__gt=timezone.now(), consumed_at__isnull=True, person__isnull=False,confirmed_at__isnull=False).first()
    if not attempt:
        return False
    attempt.consumed_at = timezone.now()
    attempt.save(update_fields=['consumed_at'])
    request.session.cycle_key()
    from django.middleware.csrf import rotate_token
    rotate_token(request)
    request.session['person_id'] = str(attempt.person_id)
    del request.session['login_token']
    return True

@transaction.atomic
def confirm_login(attempt_id, sender, chat_id, now=None):
    now=now or timezone.now()
    if not private_actor(sender,chat_id):return False
    attempt=LoginAttempt.objects.select_for_update().select_related('person').filter(pk=attempt_id,expires_at__gt=now,consumed_at__isnull=True,person__telegram_id=sender['id'],person__chat_id=chat_id).first()
    if not attempt:return False
    Person.objects.filter(pk=attempt.person_id).update(delivery_verified_at=now,delivery_blocked=False)
    if attempt.confirmed_at is None:
        attempt.confirmed_at=now
        attempt.save(update_fields=['confirmed_at'])
    return True
