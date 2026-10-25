"""Each scheduler request runs exactly one event for one Wednesday round."""
from dataclasses import dataclass
from datetime import datetime,timedelta,time
from django.db import transaction
from .clock import MOSCOW
from .models import Round,RuntimeLock,Job,Notification
from .rounds import ensure_round,RuleError
from .jobs import prepare,publish,report,complete_job,record_incident,resolve_incident
from .notifications import owner_message
from .feedback import request_times,schedule_requests
from .invitations import invitation_window,schedule_invites

EVENTS=('feedback','prepare','publish','invite')
KINDS={'feedback':('feedback_first',),'prepare':('owner_prepared',),
       'publish':('meeting','unmatched','owner_published','round_cancelled','owner_cancelled'),'invite':('signup_invite',)}

def notification_kinds(event):
    return (*KINDS[event],f'event_{event}_incident',f'event_{event}_recovery')

def window(event,start):
    r=Round(starts_at=start,ends_at=start+timedelta(days=7),closes_at=start-timedelta(hours=12))
    if event=='feedback':return request_times(r)
    if event=='invite':return invitation_window(r)
    return (r.closes_at if event=='prepare' else start),start+timedelta(hours=6)

def target_start(event,now,round_date=None):
    if event not in EVENTS:raise ValueError('Unknown event')
    if round_date is not None:
        day=datetime.strptime(round_date,'%Y-%m-%d').date()
        if day.isoformat()!=round_date or day.weekday()!=2:raise ValueError('Expected Wednesday date')
        return datetime.combine(day,time(9),MOSCOW)
    local=now.astimezone(MOSCOW)
    base=datetime.combine(local.date()-timedelta(days=(local.weekday()-2)%7),time(9),MOSCOW)
    candidates=[base+timedelta(days=offset) for offset in (-7,0,7)]
    return max((start for start in candidates if window(event,start)[0]<=now),key=lambda start:window(event,start)[0])

@dataclass
class Outcome:
    start:datetime
    round:Round|None=None
    status:str='ok'
    error:bool=False

def settle_elapsed_rounds(now):
    # Housekeeping only: no matching, publication, notifications or queue draining.
    for old in Round.objects.select_for_update().filter(state='published',ends_at__lte=now):
        old.state='completed';old.save(update_fields=['state']);complete_job('complete',old,now)
    Round.objects.filter(published_at__isnull=True,ends_at__lte=now).exclude(state__in=('completed','expired','cancelled')).update(state='expired')

@transaction.atomic
def execute(event,clock,round_date=None):
    from django.db import DatabaseError
    from .rotation import lock_rotation,ready
    from .rounds import ensure_calendar
    from .cancellations import cancel_round
    now=clock.now();start=target_start(event,now,round_date);result=Outcome(start)
    due,expiry=window(event,start)
    if now<due or (event!='publish' and now>=expiry):
        result.status='outside_window';return result
    RuntimeLock.objects.get_or_create(key='scheduler')
    lock=RuntimeLock.objects.select_for_update().get(key='scheduler')
    lock_rotation()
    ensure_calendar(now)
    settle_elapsed_rounds(now)
    r=Round.objects.select_for_update().get(pk=ensure_round(start).pk);result.round=r
    incident=f'event:{event}:{r.id}'
    placeholder_pause=(r.selection or {}).get('pause_origin')=='placeholder'
    try:
        with transaction.atomic():
            if event in ('prepare','publish') and r.state=='cancelled':
                if event=='publish':cancel_round(r.id,r.cancellation_reason,clock)
                result.status='cancelled'
            elif event=='publish':
                if r.published_at:pass
                elif r.publication_paused and not placeholder_pause:result.status='paused'
                elif now>=expiry:
                    cancel_round(r.id,'publication_missed',clock);result.status='cancelled'
                elif not ready(r.activity,r.rules_version):
                    cancel_round(r.id,'activity_unavailable',clock);result.status='cancelled'
                else:
                    if placeholder_pause and r.publication_paused:
                        r.publication_paused=False;r.selection={**r.selection,'pause_origin':'released'}
                        r.save(update_fields=['publication_paused','selection'])
                    if not r.prepared_at:
                        # Only rebuild an absent draft. prepare rejects any existing partial/manual draft.
                        if r.meetings.exists() or r.unmatched_set.exists():
                            from .matching import validate_draft
                            validate_draft(r)
                            r.state='prepared';r.prepared_at=now;r.preparation_error=''
                            r.save(update_fields=['state','prepared_at','preparation_error'])
                        else:prepare(r.id,clock)
                        complete_job('prepare',r,now)
                    publish(r.id,clock)
            elif event=='prepare':
                if not r.published_at:
                    if r.publication_paused and not placeholder_pause:
                        result.status='paused'
                    else:
                        if r.state=='open':
                            r.state='closed';r.save(update_fields=['state']);complete_job('close',r,now)
                        r=prepare(r.id,clock);complete_job('prepare',r,now)
                        if not Job.objects.filter(key=f'prepare_report:{r.id}',completed_at__isnull=False).exists():
                            if owner_message(f'prepared:{r.id}','owner_prepared',report(r),r,now):complete_job('prepare_report',r,now)
                        Round.objects.filter(pk=r.pk).update(preparation_error='')
            elif event=='feedback':
                if r.published_at:schedule_requests(r,clock)
            elif event=='invite':
                schedule_invites(r,clock)
            if result.status!='paused':complete_job('event_'+event,r,now)
            if result.status!='cancelled':resolve_incident(incident,clock,round=r,kind=f'event_{event}_recovery')
    except Exception as exc:
        error=type(exc).__name__
        Job.objects.update_or_create(key=f'event_{event}:{r.id}',defaults={'round':r,'error':error,'completed_at':None})
        if event=='prepare':Round.objects.filter(pk=r.pk).update(preparation_error=error)
        record_incident(incident,'Ошибка этапа '+event+' для раунда '+str(start.date())+' ('+error+').',clock,round=r,kind=f'event_{event}_incident')
        if isinstance(exc,(DatabaseError,OSError,TimeoutError)):
            result.error=True
        elif event=='publish':
            cancel_round(r.id,'preparation_failed',clock);result.status='cancelled'
        else:result.status='blocked'
    lock.heartbeat=now;lock.save(update_fields=['heartbeat'])
    return result

@transaction.atomic
def publication_report(round_id,clock):
    r=Round.objects.select_for_update().get(pk=round_id)
    if not r.published_at:return
    outcomes=Notification.objects.filter(round=r,kind__in=('meeting','unmatched'))
    if outcomes.filter(status__in=('pending','sending')).exists():return
    if Job.objects.filter(key=f'publication_report:{r.id}',completed_at__isnull=False).exists():return
    text=f'МАЙТИМ · раунд {r.starts_at:%d.%m}: опубликовано встреч {r.meetings.count()}, сообщений доставлено {outcomes.filter(status="sent").count()}, не доставлено/неизвестно {outcomes.exclude(status="sent").count()}.'
    if owner_message(f'published:{r.id}','owner_published',text,r,clock.now()):complete_job('publication_report',r,clock.now())
