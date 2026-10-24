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

def ensure_round(start):
    start=start.astimezone(MOSCOW)
    return Round.objects.get_or_create(starts_at=start,defaults={'ends_at':start+timedelta(days=7),'closes_at':start-timedelta(hours=12),'prepares_at':start-timedelta(hours=11)})[0]

@transaction.atomic
def enroll(person_id,round_id,active,clock):
    r=Round.objects.select_for_update().get(pk=round_id)
    p=Person.objects.select_for_update().get(pk=person_id)
    if r.state!='open' or clock.now()>=r.closes_at:
        raise RuleError('Запись закрыта. На следующий раунд можно будет записаться отдельно.')
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
