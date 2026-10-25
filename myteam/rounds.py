from datetime import datetime, timedelta, time
from django.db import transaction
from .clock import MOSCOW
from .models import Round, Enrollment, Person

class RuleError(Exception):
    pass

def upcoming_start(now):
    local=now.astimezone(MOSCOW)
    start=datetime.combine(local.date()+timedelta(days=(2-local.weekday())%7),time(9),MOSCOW)
    return start if start>now else start+timedelta(days=7)

@transaction.atomic
def ensure_round(start):
    from .activity_plan import PLANNED_ACTIVITIES
    from .activities import get_activity
    from .rotation import choose,lock_rotation
    from django.utils import timezone
    start=start.astimezone(MOSCOW)
    if start.weekday()!=2 or (start.hour,start.minute,start.second,start.microsecond)!=(9,0,0,0):
        raise RuleError('Раунд должен начинаться в среду в 09:00 МСК.')
    existing=Round.objects.filter(starts_at=start).first()
    if existing and not (existing.activity=='unavailable' and existing.state=='open' and (existing.selection or {}).get('reason')=='no_ready_activity'):return existing
    lock_rotation()
    existing=Round.objects.select_for_update().filter(starts_at=start).first()
    if existing:
        if existing.activity!='unavailable' or existing.state!='open' or existing.enrollments.exists() or existing.notification_set.exists():return existing
        activity,selection=choose(start)
        if activity:
            existing.activity=activity.key;existing.rules_version=activity.version
            existing.selection={**selection,'selected_at':timezone.now().isoformat(),'replaces_empty_placeholder':True}
            existing.save(update_fields=['activity','rules_version','selection'])
        return existing
    if start in PLANNED_ACTIVITIES:
        key,version=PLANNED_ACTIVITIES[start]
        try:activity=get_activity(key,version)
        except KeyError:activity=None
        selection={'source':'plan','title':activity.title if activity else 'Активность'}
        paused=bool(getattr(activity,'signup_only',False))
        if paused:selection['pause_origin']='placeholder'
    else:
        activity,selection=choose(start)
        key,version=(activity.key,activity.version) if activity else ('unavailable',1)
        paused=False
    selection['selected_at']=timezone.now().isoformat()
    return Round.objects.create(starts_at=start,activity=key,rules_version=version,selection=selection,
        publication_paused=paused,ends_at=start+timedelta(days=7),closes_at=start-timedelta(hours=12),prepares_at=start-timedelta(hours=12))


def ensure_calendar(now):
    # The next sign-up card must exist even if the previous publication failed.
    next_start=upcoming_start(now)
    visible_week=next_start if now>=next_start-timedelta(hours=12) else next_start-timedelta(days=7)
    for start in sorted({next_start,visible_week+timedelta(days=7)}):ensure_round(start)

@transaction.atomic
def enroll(person_id,round_id,active,clock):
    r=Round.objects.select_for_update().get(pk=round_id)
    p=Person.objects.select_for_update().get(pk=person_id)
    if r.state!='open' or clock.now()>=r.closes_at:
        raise RuleError('Запись закрыта. На следующий раунд можно будет записаться отдельно.')
    if active and r.activity=='unavailable':raise RuleError('Сейчас нет доступной активности для записи.')
    if active and (not p.complete or not p.reachable):
        raise RuleError('Заполните профиль и подключите сообщения бота перед записью.')
    if not active and not Enrollment.objects.filter(person=p,round=r).exists():
        return None
    e,created=Enrollment.objects.get_or_create(person=p,round=r,defaults={'active':active})
    if not created and e.active!=active:
        e.active=active
        e.revision+=1
        e.save(update_fields=['active','revision'])
    return e
