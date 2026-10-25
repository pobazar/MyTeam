from datetime import timedelta
from html import escape
from django.db import transaction
from .models import Round,RuntimeLock,Job,Notification,Unmatched,Incident,Member
from .rounds import ensure_round,upcoming_start,RuleError
from .matching import prepare,validate_draft
from .notifications import enqueue,owner_message
from .activities import get_activity
from .clock import MOSCOW
from django.conf import settings
from .pages import web_url

def report(r):
    lines=[f'МАЙТИМ · подготовка {r.starts_at:%d.%m} — {(r.ends_at-timedelta(hours=12)):%d.%m}',f'Записались: {r.enrollments.filter(active=True).count()}',f'Публикация: {r.starts_at.astimezone(MOSCOW):%d.%m %H:%M} МСК. Подтверждение не требуется.']
    for meeting in r.meetings.prefetch_related('members__person'):
        names=[]
        for m in meeting.members.all():
            s=m.snapshot
            names.append(escape(f'{s.get("full_name") or (s["first_name"]+" "+s["last_name"])} · {s["team"]} · {s["city"]}'))
            if s.get('team_confidence') in ('uncertain','separate','unknown'):lines.append('Команда сопоставлена неуверенно: '+escape(s['team']))
            if not m.person.reachable:lines.append('Не подтверждён канал доставки: '+escape(str(m.person)))
        lines.append(' / '.join(names))
    for item in Unmatched.objects.filter(round=r).select_related('person'):lines.append('Без собеседника: '+escape(str(item.person)))
    return '\n'.join(lines)

def record_incident(key,summary,clock):
    incident,created=Incident.objects.get_or_create(key=key,defaults={'summary':summary,'opened_at':clock.now()})
    if not created:
        incident.occurrences+=1
        if incident.resolved_at:
            incident.opened_at=clock.now();incident.resolved_at=None;incident.last_alert_at=None
        incident.summary=summary
    if not incident.last_alert_at or clock.now()-incident.last_alert_at>=timedelta(hours=24):
        n=owner_message(f'incident:{key}:{incident.opened_at.isoformat()}:{clock.now().date()}','incident','МАЙТИМ: '+escape(summary)+'\nПроверьте состояние раунда и журналы сервиса.',now=clock.now())
        if n:incident.last_alert_at=clock.now()
    incident.save()
    return incident

def resolve_incident(key,clock):
    incident=Incident.objects.filter(key=key,resolved_at__isnull=True).first()
    if incident:
        incident.resolved_at=clock.now();incident.save(update_fields=['resolved_at'])
        if incident.last_alert_at:owner_message(f'resolved:{incident.id}:{incident.opened_at.isoformat()}','recovery','МАЙТИМ: проблема устранена — '+escape(incident.summary),now=clock.now())

def complete_job(key,r,now):
    Job.objects.update_or_create(key=f'{key}:{r.id}',defaults={'round':r,'completed_at':now,'error':''})

@transaction.atomic
def publish(round_id,clock):
    r=Round.objects.select_for_update().get(pk=round_id)
    if r.published_at:return r
    if r.publication_paused:raise RuleError('Публикация приостановлена владельцем.')
    if not r.prepared_at or r.state!='prepared':raise RuleError('Нет завершённой подготовки.')
    if clock.now()<r.starts_at or clock.now()>=r.ends_at:raise RuleError('Публикация вне допустимого периода.')
    validate_draft(r)
    from .analytics import event
    for member in Member.objects.filter(round=r):
        event(f'published:{member.id}','participation',member.person,r,{'meeting_id':str(member.meeting_id),'snapshot':member.snapshot,'activity':r.activity,'rules_version':r.rules_version},clock.now())
    r.state='published';r.published_at=clock.now();r.preparation_error='';r.save(update_fields=['state','published_at','preparation_error'])
    activity=get_activity(r.activity,r.rules_version)
    for meeting in r.meetings.prefetch_related('members__person'):
        members=list(meeting.members.all())
        from .meeting_roles import persist_organizer
        organizer=persist_organizer(meeting,members)
        same_city=len({m.snapshot['city_key'] for m in members})==1
        names='\n'.join(escape(f'{m.snapshot.get("full_name") or (m.snapshot["first_name"]+" "+m.snapshot["last_name"])} · {m.snapshot["team"]} · {m.snapshot["city"]}')+(' — организатор' if str(m.person_id)==organizer else '') for m in members)
        for m in members:
            enqueue(f'meeting:{m.id}','meeting',m.person.chat_id or m.person.telegram_id,f'МАЙТИМ · {activity.title} · {r.starts_at:%d.%m} — {(r.ends_at-timedelta(hours=12)):%d.%m}\n{names}\n{('Ты организуешь встречу: предложи участникам время и место или ссылку на звонок. ' if str(m.person_id)==organizer else '')}{activity.instructions(same_city)}\n{web_url('/meetings/'+str(meeting.id)+'/')}',m.person,r,clock.now())
    for item in Unmatched.objects.filter(round=r).select_related('person'):
        enqueue(f'unmatched:{r.id}:{item.person_id}','unmatched',item.person.chat_id or item.person.telegram_id,f'МАЙТИМ · {r.starts_at:%d.%m} — {(r.ends_at-timedelta(hours=12)):%d.%m}: пока недостаточно участников для встречи. На следующий раунд можно записаться самостоятельно: {web_url('/')}. Автоматической записи нет.',item.person,r,clock.now())
    ensure_round(r.starts_at+timedelta(days=7))
    complete_job('publish',r,clock.now())
    return r

@transaction.atomic
def tick(clock):
    now=clock.now()
    RuntimeLock.objects.get_or_create(key='scheduler')
    lock=RuntimeLock.objects.select_for_update().get(key='scheduler')
    ensure_round(upcoming_start(now))
    for r in Round.objects.exclude(state__in=['completed','expired']).order_by('starts_at'):
        try:
            with transaction.atomic():
                if now>=r.ends_at:
                    if r.published_at:
                        r.state='completed';r.save(update_fields=['state']);complete_job('complete',r,now)
                    else:
                        r.state='expired';r.save(update_fields=['state'])
                        record_incident(f'round:{r.id}','Пропущена публикация раунда. Устаревшие сообщения подавлены.',clock)
                    continue
                if not r.published_at and now>=r.starts_at+timedelta(hours=6):
                    r.state='expired';r.save(update_fields=['state'])
                    record_incident(f'round:{r.id}','Публикация просрочена более чем на 6 часов. Нужна проверка.',clock)
                    continue
                if r.state=='open' and now>=r.closes_at:
                    r.state='closed';r.save(update_fields=['state']);complete_job('close',r,now)
                if now>=r.prepares_at and not r.prepared_at:
                    r=prepare(r.id,clock);complete_job('prepare',r,now)
                if r.prepared_at and not r.published_at and not Job.objects.filter(key=f'prepare_report:{r.id}',completed_at__isnull=False).exists():
                    n=owner_message(f'prepared:{r.id}','owner_prepared',report(r),r,now)
                    if n:complete_job('prepare_report',r,now)
                if now>=r.starts_at and not r.published_at:
                    if r.publication_paused:continue
                    r=publish(r.id,clock)
                if r.published_at:
                    schedule_feedback(r,clock)
                    outcomes=Notification.objects.filter(round=r,kind__in=['meeting','unmatched'])
                    if not outcomes.filter(status__in=['pending','sending']).exists() and not Job.objects.filter(key=f'publication_report:{r.id}',completed_at__isnull=False).exists():
                        n=owner_message(f'published:{r.id}','owner_published',f'МАЙТИМ · раунд {r.starts_at:%d.%m}: опубликовано встреч {r.meetings.count()}, сообщений доставлено {outcomes.filter(status="sent").count()}, не доставлено/неизвестно {outcomes.exclude(status="sent").count()}.',r,now)
                        if n:complete_job('publication_report',r,now)
                from .invitations import schedule_invites
                schedule_invites(r,clock)
                resolve_incident(f'round:{r.id}',clock)
        except Exception as error:
            # Do not persist exception text: DB/HTTP exceptions may contain credentials or personal data.
            Round.objects.filter(pk=r.id).update(preparation_error=type(error).__name__)
            Job.objects.update_or_create(key=f'error:{r.id}',defaults={'round':r,'error':type(error).__name__})
            record_incident(f'round:{r.id}','Ошибка обработки раунда '+str(r.starts_at.date())+' ('+type(error).__name__+'). Публикация заблокирована.',clock)
    lock.heartbeat=now;lock.save(update_fields=['heartbeat'])

# Populated by the feedback module; separate function keeps stage recovery in one transaction.
def schedule_feedback(r,clock):
    from .feedback import schedule_requests
    schedule_requests(r,clock)
