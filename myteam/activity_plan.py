"""Explicit future activity choices. Existing published rounds are never rewritten."""
from datetime import datetime
from .clock import MOSCOW

PLANNED_ACTIVITIES={datetime(2026,11,4,9,tzinfo=MOSCOW):('code_names',1)}


def ensure_planned_rounds(now):
    from django.db import transaction
    from .models import Round
    from .rounds import ensure_round,RuleError
    from .activities import get_activity
    result=[]
    with transaction.atomic():
        for start,(key,version) in PLANNED_ACTIVITIES.items():
            if start<=now:continue
            ensured=ensure_round(start)
            r=Round.objects.select_for_update().get(pk=ensured.pk)
            if (r.activity,r.rules_version)!=(key,version):
                if r.state!='open' or r.prepared_at or r.published_at or r.meetings.exists():
                    raise RuleError('Запланированная активность уже подготовлена; требуется ручная проверка.')
                r.activity=key;r.rules_version=version
                r.publication_paused=bool(getattr(get_activity(key,version),'signup_only',False))
                r.save(update_fields=['activity','rules_version','publication_paused'])
            result.append(r)
    return result
