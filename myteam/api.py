"""Data-only API for the static Pages client. No templates or HTML redirects."""
import json
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token,rotate_token
from django.views.decorators.http import require_http_methods,require_POST
from .clock import Clock
from .models import LoginAttempt,Round,Member,Feedback
from .users import get_person,begin_login,consume_login,digest
from .profiles import ProfileForm
from .feedback import save_feedback
from .activities import get_activity
from .rounds import enroll,RuleError
from .read_models import dashboard_context,history_entries

def response(request,data,status=200):
    return JsonResponse({**data,'csrf_token':get_token(request)},status=status)

def payload(request):
    try:
        if len(request.body)>16384:raise ValueError()
        data=json.loads(request.body)
        if not isinstance(data,dict):raise ValueError()
        return data
    except (ValueError,UnicodeDecodeError):return None

def profile_fields(person):
    return {'full_name':person.display_name,'team':person.team,'city':person.city}

def account(person):
    state='needs_onboarding' if not person.onboarding_done else 'authenticated' if person.complete else 'needs_profile'
    return {'state':state,'profile':profile_fields(person)}

def member(complete=True,achievements=False):
    def decorate(view):
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            request.person=get_person(request,achievements)
            if not request.person:return response(request,{'error':'auth_required'},401)
            state=account(request.person)
            if not request.person.onboarding_done or (complete and not request.person.complete):
                return response(request,state,409)
            return view(request,*args,**kwargs)
        return wrapped
    return decorate

def errors(form):
    return {key:[str(message) for message in messages] for key,messages in form.errors.items()}

@require_POST
def login(request):
    # This action is reached after the public, static three-step introduction.
    person=get_person(request)
    if person:
        if not person.onboarding_done:
            person.onboarding_done=True;person.save(update_fields=['onboarding_done'])
        return response(request,account(person))
    request.session['onboarding_seen']=True
    nonce=begin_login(request)
    attempt=LoginAttempt.objects.get(token_hash=digest(nonce))
    return response(request,{'code':attempt.confirmation_code,'expires_at':attempt.expires_at,
        'bot_url':f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=l_{nonce}' if settings.TELEGRAM_BOT_USERNAME else None})

@require_POST
def login_status(request):
    if request.session.get('person_id') or consume_login(request):
        person=get_person(request)
        if person:
            if request.session.pop('onboarding_seen',False) and not person.onboarding_done:
                person.onboarding_done=True;person.save(update_fields=['onboarding_done'])
            return response(request,account(person))
    nonce=request.session.get('login_token')
    valid=bool(nonce and LoginAttempt.objects.filter(token_hash=digest(nonce),expires_at__gt=Clock().now(),consumed_at__isnull=True,confirmation_code__gt='').exists())
    return response(request,{'state':'waiting','expired':not valid})

@require_POST
def logout(request):
    rotate_token(request)
    request.session.flush()
    return JsonResponse({'status':'logged_out'})

@require_POST
def onboarding(request):
    person=get_person(request)
    if not person:return response(request,{'error':'auth_required'},401)
    person.onboarding_done=True;person.save(update_fields=['onboarding_done'])
    return response(request,account(person))

@require_http_methods(['GET','POST'])
@member(complete=False,achievements=True)
def profile(request):
    if request.method=='POST':
        data=payload(request)
        if data is None:return response(request,{'error':'invalid_request'},400)
        form=ProfileForm(data,instance=request.person)
        if not form.is_valid():return response(request,{'error':'validation','fields':errors(form)},422)
        form.save()
    return response(request,{**account(request.person),'achievements':[
        {'key':'first_coffee','title':'Первый кофе','description':'Твоя первая подтверждённая встреча.'}
    ] if request.person.has_first_coffee else []})

def answer_data(answer):
    if not answer:return None
    return {'outcome':answer.outcome,'rating':answer.rating,'final':answer.final}

@require_http_methods(['GET'])
@member()
def activities(request):
    c=dashboard_context(request.person,Clock().now())
    current=c['current'];week=c['week'];n=c['next_round']
    if c['finished']:kind='completed'
    elif current:kind='active'
    elif c['unmatched']:kind='unmatched'
    elif c['current_enrolled']:kind='expired' if week.state=='expired' else 'preparing'
    else:kind='new' if c['new_here'] else 'skipped'
    return response(request,{'state':'authenticated','current':{
        'kind':kind,'starts_at':c['week_start'],'ends_at':c['week_end'],
        'activity_title':week.activity_title if week else None,'meeting_id':str(current.meeting_id) if current else None,
        'answer':answer_data(c['answer']),
        'participants':[{'name':m.snapshot.get('full_name') or f'{m.snapshot.get("first_name", "")} {m.snapshot.get("last_name", "")}'.strip(),'team':m.snapshot['team'],'city':m.snapshot['city']} for m in c['members']] if kind=='active' else [],
        'instructions':c['instructions'] if kind=='active' else None,
        'contacts_url':c['contacts_url'] if kind=='active' else None,
    },'next':{'id':str(n.id) if n else None,'starts_at':c['next_start'],'ends_at':c['next_end'],
        'closes_at':n.closes_at if n else None,'activity_title':n.activity_title if n else None,
        'enrolled':c['enrolled'],'registration_open':c['registration_open'],'reachable':request.person.reachable}})

@require_POST
@member()
def enrollment(request,round_id):
    data=payload(request)
    if not data or data.get('action') not in ('enroll','cancel'):return response(request,{'error':'invalid_request'},400)
    try:enroll(request.person.id,round_id,data['action']=='enroll',Clock())
    except Round.DoesNotExist:return response(request,{'error':'not_found'},404)
    except RuleError as e:return response(request,{'error':'enrollment_closed','message':str(e)},409)
    return response(request,{'status':'saved','enrolled':data['action']=='enroll'})

@require_http_methods(['GET'])
@member()
def history(request):
    return response(request,{'state':'authenticated','entries':[{
        'meeting_id':str(m.meeting_id),'activity_title':m.round.activity_title,
        'starts_at':m.round.starts_at,'ends_at':m.round.ends_at,'answer':answer_data(m.answer),'can_rate':m.ratable,
    } for m in history_entries(request.person,Clock().now())]})

@require_http_methods(['GET','POST'])
@member()
def feedback(request,meeting_id):
    m=Member.objects.filter(person=request.person,meeting_id=meeting_id,round__published_at__isnull=False).select_related('round','feedback').first()
    if not m:return response(request,{'error':'not_found'},404)
    existing=getattr(m,'feedback',None)
    readonly=bool(existing and existing.final and Clock().now()>=m.round.ends_at+timedelta(days=7))
    if request.method=='POST':
        data=payload(request)
        if data is None:return response(request,{'error':'invalid_request'},400)
        form=get_activity(m.round.activity,m.round.rules_version).feedback_form(data)
        if not form.is_valid():return response(request,{'error':'validation','fields':errors(form)},422)
        try:existing=save_feedback(request.person.id,meeting_id,form.cleaned_data,Clock())
        except RuleError as e:return response(request,{'error':'feedback_closed','message':str(e)},409)
        return response(request,{'status':'saved','answer':answer_data(existing)})
    return response(request,{'state':'authenticated','activity_title':m.round.activity_title,
        'starts_at':m.round.starts_at,'ends_at':m.round.ends_at,'readonly':readonly,
        'answer':{**answer_data(existing),'comment':existing.comment} if existing else None})
