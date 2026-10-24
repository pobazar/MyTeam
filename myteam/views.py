from django.http import HttpResponse, JsonResponse
def public_settings(request):
    return {}
def home(request):
    from django.shortcuts import render
    return render(request, 'myteam/home.html')
def live(request):
    return JsonResponse({'status': 'ok'})

from django.conf import settings
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils.crypto import constant_time_compare
from django.shortcuts import redirect, render
from .users import begin_login, consume_login, login_required, approve_login
from .models import TelegramUpdate
import json

def login(request):
    if request.session.get('person_id'):
        return redirect('/')
    if request.method == 'POST' and consume_login(request):
        return redirect('/')
    token = begin_login(request)
    return render(request, 'myteam/login.html', {'bot_url': f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=l_{token}' if settings.TELEGRAM_BOT_USERNAME else '', 'error': 'Вход пока не подтверждён. Откройте бота, нажмите «Старт» и вернитесь сюда.' if request.method == 'POST' else ''})

@require_POST
def logout(request):
    from django.middleware.csrf import rotate_token
    rotate_token(request)
    request.session.flush()
    return redirect('/')

@csrf_exempt
@require_POST
def telegram_webhook(request):
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not settings.TELEGRAM_WEBHOOK_SECRET or not constant_time_compare(secret, settings.TELEGRAM_WEBHOOK_SECRET):
        return HttpResponse(status=403)
    try:
        data = json.loads(request.body)
        update_id = int(data['update_id'])
    except (ValueError, KeyError, TypeError):
        return HttpResponse(status=400)
    with transaction.atomic():
        _, created = TelegramUpdate.objects.get_or_create(update_id=update_id)
        if not created:
            return JsonResponse({'ok': True})
        message = data.get('message', {})
        sender, chat = message.get('from', {}), message.get('chat', {})
        text = message.get('text', '')
        if chat.get('type') != 'private' or sender.get('id') != chat.get('id') or sender.get('is_bot'):
            return JsonResponse({'ok': True})
        if text.startswith('/start l_'):
            approve_login(text.removeprefix('/start l_').strip(), sender, chat['id'])
        elif text.startswith('/start m_'):
            from .contacts import send_contacts
            import uuid
            try:
                meeting_id=uuid.UUID(text.removeprefix('/start m_').strip())
            except ValueError:
                return JsonResponse({'ok':True})
            send_contacts(sender['id'],chat['id'],meeting_id,update_id)
    # User-initiated replies can run immediately; scheduled broadcasts remain guarded.
    from .notifications import drain
    drain(Clock(),limit=1,force=True,kinds=['bot_connected','contacts'])
    return JsonResponse({'ok': True})

from .profiles import ProfileForm
from django.db import transaction

@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.person)
    notice = ''
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
        notice = 'Профиль сохранён.'
    return render(request, 'myteam/profile.html', {'person':request.person,'form':form,'notice':notice})

ONBOARDING = [
 ('Знакомься с коллегами','МАЙТИМ помогает узнавать людей за пределами своей команды — через разговоры, игры и встречи по интересам.'),
 ('Участвуй, когда хочется','Каждую неделю — возможность пообщаться с коллегами. Форматы будут чередоваться. Участие добровольное: на каждую неделю ты записываешься сам, мы не продлеваем запись автоматически.'),
 ('Выбери ближайшую активность','Посмотри, что запланировано, и запишись, если хочешь участвовать. После подготовки мероприятия мы пришлём в Telegram участников и всё необходимое для встречи.'),
]
@login_required
def onboarding(request):
    if request.person.onboarding_done:
        return redirect('/')
    step = min(max(int(request.session.get('onboarding_step',0)),0),2)
    if request.method == 'POST':
        if request.POST.get('action')=='skip' or step==2:
            request.person.onboarding_done=True
            request.person.save(update_fields=['onboarding_done'])
            return redirect('/profile/')
        step+=1
        request.session['onboarding_step']=step
    title,body=ONBOARDING[step]
    return render(request,'myteam/onboarding.html',{'person':request.person,'heading':title,'body':body,'step':step+1})

from .models import Person, Round, Enrollment, Member
from .rounds import enroll, RuleError
from .clock import Clock

@login_required
def dashboard(request):
    if not request.person.onboarding_done:return redirect('/onboarding/')
    now=Clock().now()
    r=Round.objects.filter(starts_at__gt=now).exclude(state='expired').order_by('starts_at').first()
    current=Member.objects.filter(person=request.person,round__published_at__isnull=False,round__starts_at__lte=now,round__ends_at__gt=now).select_related('meeting','round').first()
    enrolled=bool(r and Enrollment.objects.filter(person=request.person,round=r,active=True).exists())
    return render(request,'myteam/dashboard.html',{'person':request.person,'next_round':r,'current':current,'enrolled':enrolled,'registration_open':bool(r and r.state=='open' and now<r.closes_at),'notice':request.session.pop('notice','')})

@login_required
@require_POST
def enrollment(request,round_id):
    try:
        active=request.POST.get('action')=='enroll'
        if request.POST.get('action') not in ('enroll','cancel'):return HttpResponse(status=400)
        enroll(request.person.id,round_id,active,Clock())
        request.session['notice']='Ты записан только на этот раунд. На следующий нужно записаться отдельно.' if active else 'Запись отменена. Участвуй, когда захочется.'
    except (RuleError,Round.DoesNotExist) as e:
        request.session['notice']=str(e) if isinstance(e,RuleError) else 'Раунд не найден. Обновите страницу.'
    return redirect('/')

@login_required
def reconnect(request):
    request.session.flush()
    return redirect('/login/')

_original_home=home
def home(request):
    return dashboard(request) if request.session.get('person_id') else _original_home(request)

from django.shortcuts import get_object_or_404
from .activities import get_activity
from .models import Meeting

@login_required
def meeting_detail(request,meeting_id):
    own=get_object_or_404(Member.objects.select_related('meeting','round'),person=request.person,meeting_id=meeting_id,round__published_at__isnull=False)
    members=list(own.meeting.members.all())
    same=len({m.snapshot['city_key'] for m in members})==1
    activity=get_activity(own.round.activity)
    return render(request,activity.card_template,{'person':request.person,'meeting':own.meeting,'round':own.round,'members':members,'instructions':activity.instructions(same),'contacts_url':f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=m_{meeting_id}'})

@login_required
def history(request):
    entries=Member.objects.filter(person=request.person,round__published_at__isnull=False,round__ends_at__lte=Clock().now()).select_related('round','meeting').order_by('-round__starts_at')
    return render(request,'myteam/history.html',{'person':request.person,'entries':entries})

from datetime import timedelta
from .models import Feedback
from .feedback import FeedbackForm,save_feedback

@login_required
def feedback_view(request,meeting_id):
    m=get_object_or_404(Member.objects.select_related('round'),person=request.person,meeting_id=meeting_id,round__published_at__isnull=False)
    existing=Feedback.objects.filter(member=m).first()
    readonly=Clock().now()>=m.round.ends_at+timedelta(days=7)
    initial={key:getattr(existing,key) for key in ('outcome','impression','again','comment')} if existing else {}
    form=get_activity(m.round.activity).feedback_form(request.POST if request.method=='POST' else None,initial=initial)
    notice=''
    if request.method=='POST' and not readonly and form.is_valid():
        try:
            save_feedback(request.person.id,meeting_id,form.cleaned_data,Clock())
            notice='Спасибо! Ответ сохранён.'
        except RuleError as e:form.add_error(None,str(e))
    if readonly:
        for field in form.fields.values():field.disabled=True
    return render(request,'myteam/feedback.html',{'person':request.person,'form':form,'readonly':readonly,'round':m.round,'notice':notice})

from django.db import connection

def ready(request):
    try:
        with connection.cursor() as cursor:cursor.execute('SELECT 1')
        Person.objects.exists()
    except Exception:
        return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'ok'})

def operations_health(request):
    if not settings.OPS_SECRET or not constant_time_compare(request.headers.get('Authorization',''),'Bearer '+settings.OPS_SECRET):
        return HttpResponse(status=403)
    from .monitoring import inspect
    try:
        failures=inspect(Clock())
        from .storage import available
        if not available():failures.append('storage_unavailable')
    except Exception:return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'degraded' if failures else 'ok','checks':failures},status=503 if failures else 200)

def csrf_failure(request,reason=''):
    return render(request,'403.html',status=403)
