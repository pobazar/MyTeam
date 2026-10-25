"""Choose once, persist the choice, and reuse it across requests and deployments."""
import random
from collections import Counter
from datetime import timedelta
from django.db.models import Count,Sum
from .activities import ACTIVITIES,get_activity
from .models import Round,Feedback

def lock_rotation():
    from .models import RuntimeLock
    RuntimeLock.objects.get_or_create(key='activity_rotation')
    RuntimeLock.objects.select_for_update().get(key='activity_rotation')

REQUIRED=('build_groups','valid_distribution','instructions','feedback_form','final_feedback','achievement_earned')

def ready(key,version=None):
    try:activity=get_activity(key,version)
    except KeyError:return False
    return (activity.key==key and isinstance(getattr(activity,'title',None),str) and bool(activity.title.strip())
        and isinstance(getattr(activity,'card_template',None),str) and bool(activity.card_template)
        and isinstance(getattr(activity,'achievement_key',None),str)
        and not getattr(activity,'signup_only',False) and getattr(activity,'enabled',True)
        and isinstance(getattr(activity,'minimum_participants',None),int)
        and activity.minimum_participants>0
        and all(callable(getattr(activity,name,None)) for name in REQUIRED))

def choose(start,rng=None):
    rng=rng or random.SystemRandom()
    candidates={key:a for key,a in ACTIVITIES.items() if ready(key,a.version)}
    if not candidates:
        return None,{'source':'rotation','algorithm':'weighted-variety-v1','reason':'no_ready_activity','title':'Активность'}
    past=list(Round.objects.filter(starts_at__lt=start).order_by('-starts_at').values('activity','starts_at')[:52])
    recent=[row['activity'] for row in past[:8]]
    last=past[0]['activity'] if past else None
    latest={}
    for row in past:latest.setdefault(row['activity'],row['starts_at'])
    ratings={row['member__round__activity']:row for row in Feedback.objects.filter(
        member__round__starts_at__gte=start-timedelta(weeks=26),member__round__starts_at__lt=start,
        member__round__published_at__isnull=False,outcome='yes',rating__isnull=False).values('member__round__activity').annotate(total=Sum('rating'),votes=Count('id'))}
    counts=Counter(recent);weights={};averages={}
    for key in candidates:
        rating=ratings.get(key,{})
        average=(rating.get('total',0)+3*3.5)/(rating.get('votes',0)+3)
        averages[key]=round(average,4)
        weights[key]=average/(1+counts[key])
    eligible=[key for key in candidates if key!=last] if len(candidates)>1 else list(candidates)
    # Never-used and long-absent formats cannot be starved by a popular one.
    overdue=[key for key in eligible if key not in latest or (start-latest[key]).days>=7*max(4,2*len(candidates))]
    pool=overdue or eligible
    selected=rng.choices(pool,weights=[weights[key] for key in pool],k=1)[0]
    return candidates[selected],{'source':'rotation','algorithm':'weighted-variety-v1',
        'title':candidates[selected].title,'candidates':pool,'weights':{k:round(v,4) for k,v in weights.items()},'smoothed_ratings':averages}
