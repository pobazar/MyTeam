from django.db.models.signals import post_save,post_delete
from django.dispatch import receiver
from .models import AnalyticsEvent,Enrollment,Feedback,Achievement,Notification

def event(key,kind,person=None,round=None,payload=None,now=None):
    defaults={'kind':kind,'person':person,'round':round,'payload':payload or {}}
    if now is not None:defaults['created_at']=now
    return AnalyticsEvent.objects.get_or_create(key=key,defaults=defaults)[0]

@receiver(post_save,sender=Enrollment)
def enrollment_event(sender,instance,**kwargs):
    e=instance
    event(f'enrollment:{e.id}:{e.revision}','enrolled' if e.active else 'cancelled',e.person,e.round,{'revision':e.revision})

@receiver(post_save,sender=Feedback)
def feedback_event(sender,instance,**kwargs):
    f=instance
    event(f'feedback:{f.id}:{f.revision}','feedback',f.member.person,f.member.round,{k:getattr(f,k) for k in ('outcome','rating','impression','again','comment','revision')},f.updated_at)

@receiver(post_save,sender=Notification)
def delivery(sender,instance,**kwargs):
    n=instance
    if n.status in ('sent','failed','pending','unknown','cancelled'):
        event(f'delivery:{n.id}:{n.attempts}:{n.status}','delivery',n.person,n.round,{'kind':n.kind,'status':n.status,'attempt':n.attempts,'error':n.last_error},n.sent_at)
