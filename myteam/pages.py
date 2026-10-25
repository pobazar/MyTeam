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
        if request.method=='OPTIONS' and request.headers.get('Access-Control-Request-Method'):
            response=HttpResponse(status=204 if allowed else 403)
        else:
            authorization=request.headers.get('Authorization','')
            if authorization.startswith('Bearer '):
                token=authorization.removeprefix('Bearer ')
                if not re.fullmatch('[a-z0-9]{32}',token):
                    response=JsonResponse({'error':'invalid_session'},status=401)
                else:
                    from django.contrib.sessions.backends.db import SessionStore
                    session=SessionStore(session_key=token)
                    # Load once; Django reuses the cached data for CSRF and the view.
                    session.get('person_id')
                    if session.session_key!=token:
                        response=JsonResponse({'error':'expired_session'},status=401)
                    else:
                        request.session=session
                        response=self.get_response(request)
            else:response=self.get_response(request)
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
    return JsonResponse({'session':request.session.session_key})

def web_url(path='/'):
    return settings.FRONTEND_URL.rstrip('/')+'/#'+path if settings.FRONTEND_URL else settings.PUBLIC_URL+path
