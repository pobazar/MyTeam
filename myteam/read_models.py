from datetime import timedelta
from django.conf import settings
from .models import Round,Enrollment,Member,Unmatched
from django.db.models import Exists,OuterRef,Count,Subquery,IntegerField,Value
from django.db.models.functions import Coalesce
from .activities import get_activity

def dashboard_context(person,now):
    from .rounds import upcoming_start
    next_start=upcoming_start(now)
    week_start=next_start-timedelta(days=7)
    counts=Enrollment.objects.filter(round_id=OuterRef('pk'),active=True).order_by().values('round_id').annotate(total=Count('pk')).values('total')
    rounds={item.starts_at:item for item in Round.objects.filter(starts_at__in=[week_start,next_start]).annotate(
        enrollment_count=Coalesce(Subquery(counts),Value(0),output_field=IntegerField()),
        is_enrolled=Exists(Enrollment.objects.filter(person=person,round_id=OuterRef('pk'),active=True)),
        is_unmatched=Exists(Unmatched.objects.filter(person=person,round_id=OuterRef('pk'))))}
    week=rounds.get(week_start)
    r=rounds.get(next_start)
    if r and r.state=='expired':r=None
    current=Member.objects.filter(person=person,round=week,round__published_at__isnull=False).select_related('meeting','round','feedback').first() if week and week.published_at else None
    current_enrolled=bool(week and week.is_enrolled)
    answer=getattr(current,'feedback',None) if current else None
    members=list(current.meeting.members.all()) if current else []
    activity=get_activity(week.activity,week.rules_version) if week else None
    enrolled=bool(r and r.is_enrolled)
    return {
        'person':person,'next_round':r,'next_start':next_start,'next_end':next_start+timedelta(days=7),
        'current':current,'week':week,'week_start':week_start,'week_end':next_start,'answer':answer,
        'finished':bool(answer and answer.final),'members':members,'current_enrolled':current_enrolled,
        'unmatched':bool(week and week.is_unmatched),
        'new_here':person.created_at>=week_start,'enrolled':enrolled,
        'activity_template':activity.card_template if activity else '',
        'instructions':activity.instructions(len({m.snapshot['city_key'] for m in members})==1) if current else '',
        'contacts_url':f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=m_{current.meeting_id}' if current else '',
        'registration_open':bool(r and r.state=='open' and now<r.closes_at),
    }


def history_entries(person,now):
    entries=list(Member.objects.filter(person=person,round__published_at__isnull=False,round__ends_at__lte=now).select_related('round','feedback').order_by('-round__starts_at'))
    for entry in entries:
        entry.answer=getattr(entry,'feedback',None)
        entry.ratable=not (entry.answer and entry.answer.final)
    return entries
