from django.http import HttpResponse, JsonResponse
def public_settings(request):
    person=getattr(request,'person',None)
    return {'navigation_allowed':bool(person and person.onboarding_done and person.complete)}
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
from .users import begin_login, consume_login, login_required, approve_login, confirm_login, digest
from .models import TelegramUpdate, LoginAttempt
import json

def login(request):
    if request.session.get('person_id'):
        return redirect('/')
    if request.method == 'POST' and consume_login(request):
        return redirect('/')
    token = begin_login(request)
    return render(request, 'myteam/login.html', {'login_code':LoginAttempt.objects.get(token_hash=digest(token)).confirmation_code, 'bot_url': f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=l_{token}' if settings.TELEGRAM_BOT_USERNAME else '', 'error': 'Вход пока не подтверждён. Откройте бота, нажмите «Старт» и вернитесь сюда.' if request.method == 'POST' else ''})

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
        callback=data.get('callback_query')
        if callback:
            import uuid
            sender=callback.get('from',{})
            chat=callback.get('message',{}).get('chat',{})
            accepted=False
            if chat.get('type')=='private' and callback.get('data','').startswith('login:'):
                try:attempt_id=uuid.UUID(callback['data'].removeprefix('login:'))
                except ValueError:attempt_id=None
                if attempt_id:accepted=confirm_login(attempt_id,sender,chat.get('id'))
            transaction.on_commit(lambda: answer_login_callback(callback.get('id'),accepted))
            return JsonResponse({'ok':True})
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
    drain(Clock(),limit=1,force=True,kinds=['bot_connected','contacts','bot_login'])
    return JsonResponse({'ok': True})

from .profiles import ProfileForm
from django.db import transaction

@login_required
def profile(request):
    initial_setup=not request.person.complete
    form = ProfileForm(request.POST if request.method=='POST' else None, instance=request.person)
    notice = ''
    if request.method == 'POST' and form.is_valid():
        form.save()
        if initial_setup:return redirect('/')
        notice = 'Профиль сохранён.'
    return render(request, 'myteam/profile.html', {'person':request.person,'form':form,'notice':notice,'initial_setup':initial_setup,'navigation_allowed':not initial_setup})

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
        if step==2:
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
    from .rounds import upcoming_start
    from datetime import timedelta
    from .models import Unmatched
    now=Clock().now()
    next_start=upcoming_start(now)
    week_start=next_start-timedelta(days=7)
    from django.db.models import Exists,OuterRef
    rounds={item.starts_at:item for item in Round.objects.filter(starts_at__in=[week_start,next_start]).annotate(
        is_enrolled=Exists(Enrollment.objects.filter(person=request.person,round_id=OuterRef('pk'),active=True)),
        is_unmatched=Exists(Unmatched.objects.filter(person=request.person,round_id=OuterRef('pk'))))}
    week=rounds.get(week_start)
    r=rounds.get(next_start)
    if r and r.state=='expired':r=None
    current=Member.objects.filter(person=request.person,round=week,round__published_at__isnull=False).select_related('meeting','round','feedback').first() if week and week.published_at else None
    current_enrolled=bool(week and week.is_enrolled)
    answer=getattr(current,'feedback',None) if current else None
    members=list(current.meeting.members.all()) if current else []
    activity=get_activity(week.activity,week.rules_version) if week else None
    enrolled=bool(r and r.is_enrolled)
    return render(request,'myteam/dashboard.html',{
        'person':request.person,'next_round':r,'next_start':next_start,'next_end':next_start+timedelta(days=7),
        'current':current,'week':week,'week_start':week_start,'week_end':next_start,'answer':answer,
        'finished':bool(answer and answer.final),'members':members,'current_enrolled':current_enrolled,
        'unmatched':bool(week and week.is_unmatched),
        'new_here':request.person.created_at>=week_start,'enrolled':enrolled,
        'activity_template':activity.card_template if activity else '',
        'instructions':activity.instructions(len({m.snapshot['city_key'] for m in members})==1) if current else '',
        'contacts_url':f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=m_{current.meeting_id}' if current else '',
        'registration_open':bool(r and r.state=='open' and now<r.closes_at),
        'notice':request.session.pop('notice','')})

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
    own=get_object_or_404(Member.objects.select_related('round'),person=request.person,meeting_id=meeting_id,round__published_at__isnull=False)
    return redirect('/history/' if own.round.ends_at<=Clock().now() else '/')

@login_required
def history(request):
    now=Clock().now()
    entries=list(Member.objects.filter(person=request.person,round__published_at__isnull=False,round__ends_at__lte=now).select_related('round','feedback').order_by('-round__starts_at'))
    for entry in entries:
        entry.answer=getattr(entry,'feedback',None)
        entry.ratable=not (entry.answer and entry.answer.final)
    return render(request,'myteam/history.html',{'person':request.person,'entries':entries})

from datetime import timedelta
from .models import Feedback
from .feedback import FeedbackForm,save_feedback

@login_required
def feedback_view(request,meeting_id):
    m=get_object_or_404(Member.objects.select_related('round'),person=request.person,meeting_id=meeting_id,round__published_at__isnull=False)
    existing=Feedback.objects.filter(member=m).first()
    readonly=bool(existing and existing.final and Clock().now()>=m.round.ends_at+timedelta(days=7))
    initial={key:getattr(existing,key) for key in ('outcome','rating','comment')} if existing else {}
    if initial.get('outcome')=='pending':initial['outcome']=''
    return_to='history' if request.POST.get('return_to',request.GET.get('from'))=='history' else 'activities'
    form=get_activity(m.round.activity,m.round.rules_version).feedback_form(request.POST if request.method=='POST' else None,initial=initial)
    notice=''
    if request.method=='POST' and not readonly and form.is_valid():
        try:
            save_feedback(request.person.id,meeting_id,form.cleaned_data,Clock())
            request.session['notice']='Спасибо! Результат активности сохранён.'
            return redirect('/history/' if return_to=='history' else '/')
        except RuleError as e:form.add_error(None,str(e))
    if readonly:
        for field in form.fields.values():field.disabled=True
    return render(request,'myteam/feedback.html',{'person':request.person,'form':form,'readonly':readonly,'round':m.round,'notice':notice,'return_to':return_to})

from django.db import connection

def ready(request):
    try:
        with connection.cursor() as cursor:cursor.execute('SELECT 1')
        Person.objects.exists()
    except Exception:
        return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'ok'})

def csrf_failure(request,reason=''):
    return render(request,'403.html',status=403)

@require_POST
def login_status(request):
    if request.session.get('person_id') or consume_login(request):
        return JsonResponse({'authenticated':True,'next':'/'})
    token=request.session.get('login_token')
    valid=bool(token and LoginAttempt.objects.filter(token_hash=digest(token),expires_at__gt=Clock().now(),consumed_at__isnull=True,confirmation_code__gt='').exists())
    return JsonResponse({'authenticated':False,'expired':not valid})

def answer_login_callback(callback_id,accepted):
    from .telegram import call,DeliveryError
    if not callback_id:return
    try:call('answerCallbackQuery',{'callback_query_id':callback_id,'text':'Вход подтверждён. Вернитесь на страницу МАЙТИМ.' if accepted else 'Ссылка истекла или принадлежит другому входу.'})
    except DeliveryError:pass  # Confirmation is already durable; a failed toast never revokes it.
