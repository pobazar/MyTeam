from datetime import timedelta
from .models import Round,Enrollment,Member,Unmatched
from django.db.models import Exists,OuterRef,Count,Subquery,IntegerField,Value
from django.db.models.functions import Coalesce
from .activities import get_activity

def display_week_start(now):
    from .rounds import upcoming_start
    upcoming=upcoming_start(now)
    return upcoming if now>=upcoming-timedelta(hours=12) else upcoming-timedelta(days=7)

def display_end(start):
    return start+timedelta(days=7,hours=-12)

def dashboard_context(person,now):
    from .rounds import upcoming_start
    week_start=display_week_start(now)
    next_start=week_start+timedelta(days=7)
    counts=Enrollment.objects.filter(round_id=OuterRef('pk'),active=True).order_by().values('round_id').annotate(total=Count('pk')).values('total')
    query=Round.objects.filter(starts_at__in=[week_start,next_start]).annotate(
        enrollment_count=Coalesce(Subquery(counts),Value(0),output_field=IntegerField()),
        is_enrolled=Exists(Enrollment.objects.filter(person=person,round_id=OuterRef('pk'),active=True)),
        is_unmatched=Exists(Unmatched.objects.filter(person=person,round_id=OuterRef('pk'))))
    rounds={item.starts_at:item for item in query}
    if next_start not in rounds or rounds[next_start].activity=='unavailable':
        from .rounds import ensure_round
        ensure_round(next_start)
        rounds[next_start]=query.get(starts_at=next_start)
    week=rounds.get(week_start)
    r=rounds.get(next_start)
    if r and r.state=='expired':r=None
    current=Member.objects.filter(person=person,round=week,round__published_at__isnull=False).select_related('meeting','round','feedback').first() if week and week.published_at else None
    current_enrolled=bool(week and week.is_enrolled)
    answer=getattr(current,'feedback',None) if current else None
    members=list(current.meeting.members.all()) if current else []
    from .contacts import participant_url
    for member in members:member.contact_url=participant_url(member.snapshot) if member.person_id!=person.id else None
    try:activity=get_activity(week.activity,week.rules_version) if week else None
    except KeyError:activity=None
    enrolled=bool(r and r.is_enrolled)
    return {
        'person':person,'next_round':r,'next_start':next_start,'next_end':display_end(next_start),
        'current':current,'week':week,'week_start':week_start,'week_end':display_end(week_start),'answer':answer,
        'finished':bool(answer and answer.final),'members':members,'current_enrolled':current_enrolled,
        'unmatched':bool(week and week.is_unmatched),
        'new_here':person.created_at>=week_start,'enrolled':enrolled,'awaiting_publication':now<week_start,
        'activity_template':activity.card_template if activity else '',
        'instructions':activity.instructions(len({m.snapshot['city_key'] for m in members})==1) if current and activity else '',
        'registration_open':bool(r and r.activity!='unavailable' and r.state=='open' and now<r.closes_at),
    }


def history_entries(person,now):
    entries=list(Member.objects.filter(person=person,round__published_at__isnull=False,round__starts_at__lt=display_week_start(now)).select_related('round','feedback').order_by('-round__starts_at'))
    for entry in entries:
        entry.answer=getattr(entry,'feedback',None)
        entry.ratable=not (entry.answer and entry.answer.final)
    return entries
