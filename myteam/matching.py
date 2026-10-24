from itertools import combinations
import random
import networkx as nx
from django.db import transaction
from .models import Round, Enrollment, Meeting, Member, Unmatched
from .rounds import RuleError

def snapshot(p):
    return {'first_name':p.first_name,'last_name':p.last_name,'team':p.team,'team_group':str(p.team_group_id) if p.team_group_id else None,'team_confidence':p.team_confidence,'city':p.city,'city_key':p.city_key,'telegram_id':p.telegram_id,'username':p.username}

def select_groups(people, history, rng=None):
    """Minimum-weight perfect matching; one triple for odd attendance."""
    rng=rng or random.SystemRandom()
    count=len(people)
    if count<2:return []
    people=list(people)
    rng.shuffle(people)
    # Integer scales guarantee total lower-priority costs never overtake one higher priority.
    edges=count*(count-1)//2
    max_recency=max(history.values(),default=0)
    random_scale=edges*1001+1
    team_scale=random_scale
    recency_scale=(edges+1)*team_scale
    repeat_scale=(edges*(max_recency+1)+1)*recency_scale
    costs={}
    for a,b in combinations(range(count),2):
        key=frozenset((people[a].id,people[b].id))
        repeated=key in history
        same=people[a].team_group_id is not None and people[a].team_group_id==people[b].team_group_id
        costs[a,b]=int(repeated)*repeat_scale+history.get(key,0)*recency_scale+int(same)*team_scale+rng.randrange(1000)
    def edge(a,b):return costs[tuple(sorted((a,b)))]
    def pairs(indices):
        graph=nx.Graph()
        graph.add_nodes_from(indices)
        for a,b in combinations(indices,2):graph.add_edge(a,b,weight=edge(a,b))
        return [list(pair) for pair in nx.min_weight_matching(graph)]
    if count%2==0:
        groups=pairs(list(range(count)))
    else:
        if count<=21:
            triples=list(combinations(range(count),3))
        else:
            candidates=set()
            while len(candidates)<128:candidates.add(tuple(sorted(rng.sample(range(count),3))))
            triples=list(candidates)
        best=None
        for triple in triples:
            rest=pairs([i for i in range(count) if i not in triple])
            groups=[list(triple),*rest]
            cost=sum(edge(a,b) for group in groups for a,b in combinations(group,2))
            if best is None or cost<best[0]:best=(cost,groups)
        groups=best[1]
    return [[people[i] for i in group] for group in groups]

def validate_draft(r):
    expected=set(r.enrollments.filter(active=True).values_list('person_id',flat=True))
    seen=[]
    meetings=list(r.meetings.prefetch_related('members'))
    for meeting in meetings:
        members=list(meeting.members.all())
        if len(members) not in (2,3) or any(m.round_id!=r.id for m in members):
            raise RuleError('Некорректный размер или принадлежность группы.')
        for m in members:
            if not all(m.snapshot.get(k) for k in ('first_name','last_name','team','city','city_key','telegram_id')):
                raise RuleError('Неполный снимок профиля.')
        seen.extend(m.person_id for m in members)
    if Member.objects.filter(round=r).exclude(meeting__round=r).exists():raise RuleError('Связи раунда повреждены.')
    unmatched=list(Unmatched.objects.filter(round=r).values_list('person_id',flat=True))
    if any(x.reason!='insufficient_participants' for x in Unmatched.objects.filter(round=r)):
        raise RuleError('Некорректная причина отсутствия встречи.')
    if len(seen)!=len(set(seen)) or set(seen)&set(unmatched) or set(seen+unmatched)!=expected:
        raise RuleError('Состав не соответствует закрытым записям.')
    if len(expected)==1:
        if len(unmatched)!=1 or meetings:raise RuleError('Неверный результат для одного участника.')
    elif unmatched:raise RuleError('Участники остались без группы.')
    if sum(meeting.members.count()==3 for meeting in meetings)!=(1 if len(expected)>=3 and len(expected)%2 else 0):
        raise RuleError('Неверное количество троек.')
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
    for meeting in Meeting.objects.filter(round__published_at__isnull=False).order_by('round__starts_at').prefetch_related('members'):
        age=int(meeting.round.starts_at.timestamp()//86400)
        for a,b in combinations(meeting.members.all(),2):history[frozenset((a.person_id,b.person_id))]=age
    if len(people)==1:Unmatched.objects.create(round=r,person=people[0])
    for group in select_groups(people,history):
        meeting=Meeting.objects.create(round=r,activity_data={'rules_version':r.rules_version})
        for p in group:Member.objects.create(meeting=meeting,round=r,person=p,snapshot=snapshot(p))
    validate_draft(r)
    r.prepared_at=clock.now()
    r.state='prepared'
    r.preparation_error=''
    r.save(update_fields=['prepared_at','state','preparation_error'])
    return r
