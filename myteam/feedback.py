from datetime import timedelta
from django import forms
from django.conf import settings
from django.db import transaction
from .clock import MOSCOW
from .models import Member,Feedback,Achievement,Person,Job
from .notifications import enqueue
from .rounds import RuleError
from .pages import web_url
from .activities import get_activity

class FeedbackForm(forms.Form):
    outcome=forms.ChoiceField(label='Получилось провести активность?',choices=[('yes','Да'),('no','Нет')],widget=forms.RadioSelect)
    rating=forms.TypedChoiceField(label='Оцените активность',required=False,choices=[(str(i),f'{i} из 5') for i in range(1,6)],coerce=int,empty_value=None,widget=forms.RadioSelect)
    comment=forms.CharField(label='Комментарий',max_length=3000,required=False,widget=forms.Textarea(attrs={'rows':3}))
    def clean(self):
        data=super().clean()
        if data.get('outcome')=='yes' and not data.get('rating'):
            self.add_error('rating','Оцените активность от 1 до 5.')
        if data.get('outcome')=='no':
            data['rating']=None
            if not data.get('comment'):self.add_error('comment','Расскажите, почему не получилось провести активность.')
        return data

@transaction.atomic
def save_feedback(person_id,meeting_id,data,clock):
    Person.objects.select_for_update().get(pk=person_id)
    m=Member.objects.select_for_update(of=('self',)).select_related('round').get(person_id=person_id,meeting_id=meeting_id,round__published_at__isnull=False)
    existing=Feedback.objects.filter(member=m).first()
    if clock.now()<m.round.starts_at or (existing and existing.final and clock.now()>=m.round.ends_at+timedelta(days=7)):
        raise RuleError('Срок изменения обратной связи закончился. Ответ доступен для просмотра.')
    activity=get_activity(m.round.activity,m.round.rules_version)
    form=activity.feedback_form(data)
    if not form.is_valid():raise RuleError('Проверьте обязательные ответы.')
    f,created=Feedback.objects.get_or_create(member=m,defaults={**form.cleaned_data,'updated_at':clock.now()})
    if not created and any(getattr(f,k)!=v for k,v in form.cleaned_data.items()):
        for k,v in form.cleaned_data.items():setattr(f,k,v)
        f.revision+=1;f.updated_at=clock.now();f.save()
    if activity.achievement_earned(person_id):
        achievement,awarded=Achievement.objects.get_or_create(person_id=person_id,key=activity.achievement_key,defaults={'created_at':clock.now()})
        if awarded:
            from .analytics import event
            event(f'achievement:{achievement.id}:awarded','achievement_awarded',m.person,m.round,{'key':activity.achievement_key},clock.now())
    else:
        from .analytics import event
        for achievement in Achievement.objects.filter(person_id=person_id,key=activity.achievement_key):
            event(f'achievement:{achievement.id}:revoked','achievement_revoked',m.person,m.round,{'key':activity.achievement_key},clock.now())
            achievement.delete()
    return f

def request_times(r):
    tuesday=(r.starts_at.astimezone(MOSCOW)+timedelta(days=6)).replace(hour=settings.FEEDBACK_HOUR,minute=settings.FEEDBACK_MINUTE,second=0,microsecond=0)
    return tuesday,r.ends_at

@transaction.atomic
def schedule_requests(r,clock):
    if not r.published_at:return
    now=clock.now()
    due,expiry=request_times(r)
    # Keep feedback_first identity so an already requested round is not requested again.
    kind='feedback_first'
    if not due<=now<expiry or Job.objects.filter(key=f'{kind}:{r.id}',completed_at__isnull=False).exists():return
    for member in Member.objects.filter(round=r).select_related('person'):
        if not member.person.reachable:continue
        f=Feedback.objects.filter(member=member).first()
        if f and f.final:continue
        enqueue(f'{kind}:{member.id}',kind,member.person.chat_id or member.person.telegram_id,f'МАЙТИМ · Как прошла встреча?\n{get_activity(r.activity,r.rules_version).title} {r.starts_at:%d.%m} — {r.ends_at:%d.%m}. Поделись впечатлениями: {web_url('/meetings/'+str(member.meeting_id)+'/feedback/')}',member.person,r,now)
    Job.objects.update_or_create(key=f'{kind}:{r.id}',defaults={'round':r,'completed_at':now,'error':''})
