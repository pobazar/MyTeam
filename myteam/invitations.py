"""One Thursday invitation per reachable, onboarded user and upcoming round."""
from datetime import timedelta
from django.db import transaction
from .clock import MOSCOW
from .models import Enrollment, Job, Person
from .notifications import enqueue

def invitation_window(r):
    # The upcoming Wednesday round opens after the previous Wednesday publication.
    due=(r.starts_at.astimezone(MOSCOW)-timedelta(days=6)).replace(hour=9,minute=0,second=0,microsecond=0)
    # Do not turn a missed Thursday broadcast into a Friday/Tuesday surprise.
    return due,min(due+timedelta(hours=6),r.closes_at)

@transaction.atomic
def schedule_invites(r,clock):
    now=clock.now()
    due,expiry=invitation_window(r)
    key=f'signup_invite:{r.id}'
    if r.state!='open' or not due<=now<expiry or Job.objects.filter(key=key,completed_at__isnull=False).exists():return
    enrolled=Enrollment.objects.filter(round=r,active=True).values('person_id')
    people=Person.objects.filter(onboarding_done=True,chat_id__isnull=False,delivery_verified_at__isnull=False,delivery_blocked=False).exclude(id__in=enrolled)
    for person in people:
        from .user_messages import invitation
        text,payload=invitation(r)
        enqueue(f'signup_invite:{r.id}:{person.id}','signup_invite',person.chat_id,text,person,r,now,payload=payload)
    Job.objects.update_or_create(key=key,defaults={'round':r,'completed_at':now,'error':''})
