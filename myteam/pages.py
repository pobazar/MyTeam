"""Same Django sessions for the static Pages client; no third-party cookies required."""
import re
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.utils.cache import patch_vary_headers

class PagesSessionMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        origin=request.headers.get('Origin','')
        allowed=origin in settings.FRONTEND_ORIGINS
        logout_request=request.path=='/api/logout/' and request.method=='POST'
        if request.method=='OPTIONS' and request.headers.get('Access-Control-Request-Method'):
            response=HttpResponse(status=204 if allowed else 403)
        else:
            authorization=request.headers.get('Authorization','')
            if authorization.startswith('Bearer '):
                token=authorization.removeprefix('Bearer ')
                if not re.fullmatch('[a-z0-9]{32}',token):
                    response=JsonResponse({'status':'logged_out'}) if logout_request else JsonResponse({'error':'invalid_session'},status=401)
                else:
                    from django.contrib.sessions.backends.db import SessionStore
                    session=SessionStore(session_key=token)
                    # Load once; Django reuses the cached data for CSRF and the view.
                    session.get('person_id')
                    if session.session_key!=token:
                        response=JsonResponse({'status':'logged_out'}) if logout_request else JsonResponse({'error':'expired_session'},status=401)
                    else:
                        request.session=session
                        response=self.get_response(request)
            else:response=self.get_response(request)
        # Sliding expiry for authenticated Pages requests. Ordinary reads need only
        # one UPDATE, not a full session rewrite/transaction on every screen load.
        # Modified sessions are saved (with the new expiry) by SessionMiddleware.
        session=getattr(request,'session',None)
        if (request.headers.get('Authorization','').startswith('Bearer ')
                and request.path.startswith('/api/') and request.method!='OPTIONS'
                and (200<=response.status_code<400 or response.status_code in (409,422))
                and session is not None and not session.modified
                and session.session_key and session.get('person_id')):
            from django.contrib.sessions.models import Session
            from django.db.models.functions import Greatest
            from django.utils import timezone
            # Update only a still-live row; concurrent logout must never recreate it.
            Session.objects.filter(session_key=session.session_key,expire_date__gt=timezone.now()).update(
                expire_date=Greatest('expire_date',session.get_expiry_date()))
        if request.path.startswith('/api/') and request.method!='OPTIONS' and not response.get('Content-Type','').startswith('application/json'):
            # Framework 404/405/500 and accidental redirects also remain data-only.
            status=response.status_code
            code={404:'not_found',405:'method_not_allowed',403:'forbidden'}.get(status,'server_error')
            if status<400:status=400 if status>=300 else 500
            allowed_methods=response.get('Allow')
            response=JsonResponse({'error':code},status=status)
            if allowed_methods:response['Allow']=allowed_methods
        response['Cache-Control']='no-store'
        if allowed:
            response['Access-Control-Allow-Origin']=origin
            response['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
            response['Access-Control-Allow-Headers']='Authorization, Content-Type, X-CSRFToken'
            response['Access-Control-Expose-Headers']='X-Myteam-Session, Server-Timing'
            response['Access-Control-Max-Age']='600'
            if getattr(request,'session',None) is not None and request.session.session_key and (request.session.modified or request.path=='/bridge/bootstrap/'):
                response['X-Myteam-Session']=request.session.session_key
        patch_vary_headers(response,['Origin'])
        return response

def bootstrap(request):
    if request.method!='GET' or request.headers.get('Origin') not in settings.FRONTEND_ORIGINS:
        return HttpResponse(status=403)
    if not request.session.session_key:request.session.create()
    from django.middleware.csrf import get_token
    return JsonResponse({'session':request.session.session_key,'csrf_token':get_token(request)})

def web_url(path='/'):
    return settings.FRONTEND_URL.rstrip('/')+'/#'+path if settings.FRONTEND_URL else settings.PUBLIC_URL+path
