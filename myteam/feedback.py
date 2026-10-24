from datetime import timedelta
from django import forms
from django.conf import settings
from django.db import transaction
from .clock import MOSCOW
from .models import Member,Feedback,Achievement,Person
from .notifications import enqueue
from .rounds import RuleError

class FeedbackForm(forms.Form):
    outcome=forms.ChoiceField(label='Удалось встретиться?',choices=[('','Выбери ответ'),('yes','Да'),('pending','Пока нет'),('no','Не получилось')])
    impression=forms.ChoiceField(label='Если да: как прошла встреча?',required=False,choices=[('','Выбери ответ'),('positive','Понравилось'),('neutral','Нейтрально'),('negative','Не понравилось')])
    again=forms.ChoiceField(label='Если да: хочется поучаствовать ещё?',required=False,choices=[('','Выбери ответ'),('yes','Да'),('maybe','Возможно'),('no','Нет')])
    comment=forms.CharField(label='Комментарий (необязательно)',max_length=3000,required=False,widget=forms.Textarea)
    def clean(self):
        data=super().clean()
        if data.get('outcome')=='yes':
            for key in ('impression','again'):
                if not data.get(key):self.add_error(key,'Выбери ответ, чтобы подтвердить встречу.')
        else:
            data['impression']='';data['again']=''
        return data

@transaction.atomic
def save_feedback(person_id,meeting_id,data,clock):
    Person.objects.select_for_update().get(pk=person_id)
    m=Member.objects.select_for_update().select_related('round').get(person_id=person_id,meeting_id=meeting_id,round__published_at__isnull=False)
    if clock.now()<m.round.starts_at or clock.now()>=m.round.ends_at+timedelta(days=7):
        raise RuleError('Срок изменения обратной связи закончился. Ответ доступен для просмотра.')
    form=FeedbackForm(data)
    if not form.is_valid():raise RuleError('Проверьте обязательные ответы.')
    f,created=Feedback.objects.get_or_create(member=m,defaults={**form.cleaned_data,'updated_at':clock.now()})
    if not created and any(getattr(f,k)!=v for k,v in form.cleaned_data.items()):
        for k,v in form.cleaned_data.items():setattr(f,k,v)
        f.revision+=1;f.updated_at=clock.now();f.save()
    if Feedback.objects.filter(member__person_id=person_id,outcome='yes').exists():
        achievement,awarded=Achievement.objects.get_or_create(person_id=person_id,key='first_coffee',defaults={'created_at':clock.now()})
        if awarded:
            from .analytics import event
            event(f'achievement:{achievement.id}:awarded','achievement_awarded',m.person,m.round,{'key':'first_coffee'},clock.now())
    else:
        from .analytics import event
        for achievement in Achievement.objects.filter(person_id=person_id,key='first_coffee'):
            event(f'achievement:{achievement.id}:revoked','achievement_revoked',m.person,m.round,{'key':'first_coffee'},clock.now())
            achievement.delete()
    return f

def request_times(r):
    monday=(r.starts_at.astimezone(MOSCOW)+timedelta(days=5)).replace(hour=settings.FEEDBACK_HOUR,minute=settings.FEEDBACK_MINUTE,second=0,microsecond=0)
    return monday,r.ends_at.astimezone(MOSCOW)-timedelta(hours=12)

def schedule_requests(r,clock):
    if not r.published_at:return
    now=clock.now()
    first,last=request_times(r)
    for kind,due,expiry in (('feedback_first',first,last),('feedback_last',last,r.ends_at)):
        if due<=now<expiry:
            for m in r.meetings.values_list('members__id',flat=True):
                member=Member.objects.select_related('person').get(pk=m)
                f=Feedback.objects.filter(member=member).first()
                if f and f.final:continue
                title='Последнее напоминание' if kind=='feedback_last' else 'Как прошла встреча?'
                enqueue(f'{kind}:{member.id}',kind,member.person.chat_id or member.person.telegram_id,f'МАЙТИМ · {title}\nRandom Coffee {r.starts_at:%d.%m} — {r.ends_at:%d.%m}. Поделись впечатлениями: {settings.PUBLIC_URL}/meetings/{member.meeting_id}/feedback/',member.person,r,now)
