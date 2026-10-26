"""Explicit future activity choices. Existing published rounds are never rewritten."""
from datetime import datetime
from .clock import MOSCOW

PLANNED_ACTIVITIES={
    datetime(2026,10,28,9,tzinfo=MOSCOW):('random_coffee',1),
    datetime(2026,11,4,9,tzinfo=MOSCOW):('code_names',1),
}


def ensure_planned_rounds(now):
    from django.db import transaction
    from .models import Round
    from .rounds import ensure_round
    from .activities import get_activity
    result=[]
    with transaction.atomic():
        from .rotation import lock_rotation
        lock_rotation()
        for start,(key,version) in PLANNED_ACTIVITIES.items():
            if start<=now:continue
            ensured=ensure_round(start)
            r=Round.objects.select_for_update().get(pk=ensured.pk)
            if (r.activity,r.rules_version)!=(key,version):
                if r.state!='open' or r.prepared_at or r.published_at or r.meetings.exists():
                    continue
                if r.enrollments.exists() or r.notification_set.exists() or (r.selection or {}).get('source')=='manual':
                    continue
                r.activity=key;r.rules_version=version
                try:activity=get_activity(key,version)
                except KeyError:activity=None
                r.selection={'source':'plan','title':activity.title if activity else 'Активность'}
                if getattr(activity,'signup_only',False):r.selection['pause_origin']='placeholder'
                r.publication_paused=bool(getattr(activity,'signup_only',False))
                r.save(update_fields=['activity','rules_version','publication_paused','selection'])
            result.append(r)
    return result
