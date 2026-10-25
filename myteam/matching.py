from itertools import combinations
from django.db import transaction
from .models import Round, Enrollment, Meeting, Member, Unmatched
from .rounds import RuleError
from .activities import get_activity
from .activities.coffee import select_groups

def snapshot(p):
    return {'full_name':p.display_name,'first_name':p.first_name,'last_name':p.last_name,'team':p.team,'team_group':str(p.team_group_id) if p.team_group_id else None,'team_confidence':p.team_confidence,'city':p.city,'city_key':p.city_key,'telegram_id':p.telegram_id,'username':p.username}


def validate_draft(r):
    activity=get_activity(r.activity,r.rules_version)
    expected=set(r.enrollments.filter(active=True).values_list('person_id',flat=True))
    seen=[]
    meetings=list(r.meetings.prefetch_related('members'))
    for meeting in meetings:
        members=list(meeting.members.all())
        if any(m.round_id!=r.id for m in members):
            raise RuleError('Некорректный размер или принадлежность группы.')
        for m in members:
            has_name=bool(m.snapshot.get('full_name') or (m.snapshot.get('first_name') and m.snapshot.get('last_name')))
            if not has_name or not all(m.snapshot.get(k) for k in ('team','city','city_key','telegram_id')):
                raise RuleError('Неполный снимок профиля.')
        seen.extend(m.person_id for m in members)
    if Member.objects.filter(round=r).exclude(meeting__round=r).exists():raise RuleError('Связи раунда повреждены.')
    unmatched=list(Unmatched.objects.filter(round=r).values_list('person_id',flat=True))
    if any(x.reason!='insufficient_participants' for x in Unmatched.objects.filter(round=r)):
        raise RuleError('Некорректная причина отсутствия встречи.')
    if len(seen)!=len(set(seen)) or set(seen)&set(unmatched) or set(seen+unmatched)!=expected:
        raise RuleError('Состав не соответствует закрытым записям.')
    if not activity.valid_distribution(len(expected),[len(m.members.all()) for m in meetings],len(unmatched)):
        raise RuleError('Состав не соответствует правилам активности.')
    return True

@transaction.atomic
def prepare(round_id,clock):
    r=Round.objects.select_for_update().get(pk=round_id)
    if r.prepared_at:
        return r
    if clock.now()<r.prepares_at or r.state not in ('open','closed'):
        raise RuleError('Подготовка недоступна в этом состоянии.')
    if r.meetings.exists() or Member.objects.filter(round=r).exists() or Unmatched.objects.filter(round=r).exists():
        raise RuleError('Обнаружен незавершённый состав. Требуется проверка владельца.')
    people=[e.person for e in Enrollment.objects.filter(round=r,active=True).select_related('person')]
    history={}
    for meeting in Meeting.objects.filter(round__published_at__isnull=False).select_related('round').order_by('round__starts_at').prefetch_related('members'):
        age=int(meeting.round.starts_at.timestamp()//86400)
        for a,b in combinations(meeting.members.all(),2):history[frozenset((a.person_id,b.person_id))]=age
    activity=get_activity(r.activity,r.rules_version)
    if len(people)<activity.minimum_participants:
        for person in people:Unmatched.objects.create(round=r,person=person)
    for group in activity.build_groups(people,history):
        meeting=Meeting.objects.create(round=r,activity_data={'rules_version':r.rules_version})
        for p in group:Member.objects.create(meeting=meeting,round=r,person=p,snapshot=snapshot(p))
    validate_draft(r)
    r.prepared_at=clock.now()
    r.state='prepared'
    r.preparation_error=''
    r.save(update_fields=['prepared_at','state','preparation_error'])
    return r
