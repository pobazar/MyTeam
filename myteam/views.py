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
