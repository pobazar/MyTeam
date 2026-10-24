from datetime import timedelta
from html import escape
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Notification, Person, Feedback, Member
from .telegram import send, DeliveryError

def enqueue(key, kind, chat_id, text, person=None, round=None, now=None):
    return Notification.objects.get_or_create(key=key, defaults={'kind':kind,'chat_id':chat_id,'text':text,'person':person,'round':round,'next_attempt_at':now or timezone.now()})[0]

def owner_message(key, kind, text, round=None, now=None):
    if not settings.OWNER_CHAT_ID or not settings.OWNER_TELEGRAM_ID:
        return None
    owner = Person.objects.filter(telegram_id=settings.OWNER_TELEGRAM_ID, chat_id=settings.OWNER_CHAT_ID, delivery_verified_at__isnull=False, delivery_blocked=False).first()
    if not owner:
        return None
    # Telegram supports 4096 chars; reports may contain every pair/triple.
    parts = []
    current = ''
    for line in text.splitlines(keepends=True):
        if len(current)+len(line)>3500:
            parts.append(current)
            current=''
        current+=line
    if current:parts.append(current)
    result=None
    for i,part in enumerate(parts):
        result=enqueue(f'{key}:{i}',kind,int(settings.OWNER_CHAT_ID),part,owner,round,now)
    return result

def eligible(notification, now):
    if notification.person_id:
        p = Person.objects.get(pk=notification.person_id)
        if (notification.kind!='bot_connected' and not p.reachable) or p.chat_id!=notification.chat_id:
            return False
    if notification.kind.startswith('feedback'):
        r=notification.round
        if not r or now>=r.ends_at:
            return False
        if notification.kind=='feedback_first':
            from .feedback import request_times
            if now>=request_times(r)[1]:return False
        f=Feedback.objects.filter(member__person_id=notification.person_id, member__round=r).first()
        return not (f and f.final) and Member.objects.filter(person_id=notification.person_id,round=r).exists()
    if notification.kind in ('meeting','unmatched') and now>=notification.round.ends_at:
        return False
    return True

def drain(clock, transport=None, limit=20, force=False):
    if not settings.SEND_TELEGRAM and not force:
        return 0
    transport = transport or send
    now=clock.now()
    # A crashed sender may have delivered its leased message: never silently resend.
    with transaction.atomic():
        for expired in Notification.objects.select_for_update(skip_locked=True).filter(status='sending',leased_until__lt=now):
            expired.status='unknown';expired.last_error='worker_interrupted_unknown'
            expired.save(update_fields=['status','last_error'])
    processed=0
    for _ in range(limit):
        with transaction.atomic():
            n=Notification.objects.select_for_update(skip_locked=True).filter(status='pending',next_attempt_at__lte=now).order_by('next_attempt_at','created_at').first()
            if n is None:break
            if not eligible(n,now):
                n.status='cancelled'
                n.save(update_fields=['status'])
                continue
            n.status='sending'
            n.attempts+=1
            n.leased_until=now+timedelta(minutes=5)
            n.save(update_fields=['status','attempts','leased_until'])
        try:
            message_id=transport(n.chat_id,n.text)
        except DeliveryError as e:
            n.last_error=e.code
            n.status='unknown' if e.uncertain else 'failed' if e.permanent or n.attempts>=8 else 'pending'
            n.next_attempt_at=now+timedelta(seconds=max(60,e.retry_after,min(3600,30*2**n.attempts)))
            if e.code=='telegram_403' and n.person_id:
                Person.objects.filter(pk=n.person_id).update(delivery_blocked=True)
        else:
            n.status='sent'
            n.sent_at=clock.now()
            n.telegram_message_id=message_id
            if n.kind=='bot_connected' and n.person_id:
                Person.objects.filter(pk=n.person_id).update(delivery_verified_at=n.sent_at,delivery_blocked=False)
        n.leased_until=None
        with transaction.atomic():
            n.save(update_fields=['status','last_error','next_attempt_at','sent_at','telegram_message_id','leased_until'])
        processed+=1
    return processed
