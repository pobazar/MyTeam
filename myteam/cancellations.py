"""A failed unpublished round has a durable terminal outcome and one notice per enrollee."""
from datetime import timedelta
from django.db import transaction
from .models import Round,Enrollment,Notification,Incident
from .notifications import enqueue,owner_message
from .user_messages import link_button
from html import escape

@transaction.atomic
def cancel_round(round_id,reason,clock):
    r=Round.objects.select_for_update().get(pk=round_id)
    if r.published_at:return r
    if r.state!='cancelled':
        r.state='cancelled';r.cancelled_at=clock.now();r.cancellation_reason=reason
        r.save(update_fields=['state','cancelled_at','cancellation_reason'])
    # Preserve draft, registrations and all history. Never send obsolete assignments.
    Notification.objects.filter(round=r,kind__in=('meeting','unmatched'),status='pending').update(status='cancelled')
    if clock.now()<r.ends_at-timedelta(hours=12):
        text=escape(r.activity_title)+'\n\nНа этой неделе активность не состоится: её не удалось подготовить. Запись на следующую активность открывается отдельно.'
        for e in Enrollment.objects.filter(round=r,active=True).select_related('person'):
            p=e.person
            enqueue(f'round_cancelled:{r.id}:{p.id}','round_cancelled',p.chat_id or p.telegram_id,text,p,r,clock.now(),payload=link_button('Открыть активности','/'))
    Incident.objects.filter(key__in=(f'event:prepare:{r.id}',f'event:publish:{r.id}'),resolved_at__isnull=True).update(resolved_at=clock.now())
    owner_message(f'owner_cancelled:{r.id}','owner_cancelled','МАЙТИМ · '+escape(r.activity_title)+': активность отменена. Записавшиеся участники получат уведомление; запись на следующую неделю сохранена отдельно.',r,clock.now())
    return r
