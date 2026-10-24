"""GitHub Actions runner: short-lived OIDC identity, bounded recovery, no shared secrets."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API='https://myteam-web.onrender.com'
ENDPOINT=API+'/internal/schedule/'

def request(url,headers=None,data=None,timeout=45):
    # Never follow a redirect carrying the GitHub credential or signed identity.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url,data=data,headers=headers or {}),timeout=timeout) as r:
        return json.load(r)

def identity():
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    url+=('&' if '?' in url else '?')+urllib.parse.urlencode({'audience':API})
    result=request(url,{'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']},timeout=20)
    return result['value']

def main():
    verify=os.getenv('MYTEAM_VERIFY_ONLY')=='true'
    deadline=time.monotonic()+70*60
    while time.monotonic()<deadline:
        try:
            # A cold free Render instance can take longer than a request timeout to wake up.
            request(API+'/health/ready',timeout=45)
            token=identity()
            result=request(ENDPOINT,{'Content-Type':'application/json','X-Myteam-Scheduler-Token':token},json.dumps({'mode':'verify' if verify else 'run'}).encode())
            if verify:
                if result.get('status')!='verified':raise ValueError()
                print('GitHub identity and backend database verified. No stages or deliveries executed.')
                return 0
            print('Event batch:',json.dumps({k:result.get(k) for k in ('status','processed','pending','stage_errors')}))
            if result.get('status')=='ok' and result.get('pending')==0:return 0
            delay=max(1,min(60,int(result.get('retry_after') or 30)))
        except urllib.error.HTTPError as error:
            # No exception bodies or URLs: they can contain credentials.
            print('Request HTTP status:',error.code)
            if error.code in (400,401,403,404):return 1
            delay=30
        except (OSError,ValueError,KeyError):
            print('Temporary request failure; retrying safely.')
            delay=30
        time.sleep(min(delay,max(0,deadline-time.monotonic())))
    print('Recovery window exhausted. Pending work is durable; inspect the workflow and Render before retrying.')
    return 1

if __name__=='__main__':sys.exit(main())
