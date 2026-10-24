"""Independent GitHub runner; keeps delivery state in a restricted Actions artifact.
No application DB is needed. Never print HTTP exception URLs (bot token) or bodies.
"""
import io
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import zipfile

PAGES_URL = 'https://pobazar.github.io/MyTeam/'
API_URL = 'https://myteam-web.onrender.com'
OWNER_CHAT_ID = 776767993

STATE=Path('monitor-state/state.json')
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result and __import__('urllib.parse',fromlist=['urlsplit']).urlsplit(req.full_url).hostname!=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(newurl).hostname:
            result.remove_header('Authorization')
        return result
OPENER=urllib.request.build_opener(SafeRedirect())
def request(url,token=None,payload=None,timeout=60):
    headers={'Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    data=json.dumps(payload).encode() if payload is not None else None
    if data:headers['Content-Type']='application/json'
    with OPENER.open(urllib.request.Request(url,data=data,headers=headers),timeout=timeout) as r:return r.read()

def restore():
    repo=os.environ['GITHUB_REPOSITORY']
    token=os.environ['GH_TOKEN']
    data=json.loads(request(f'https://api.github.com/repos/{repo}/actions/artifacts?name=myteam-monitor-state&per_page=10',token))
    artifacts=[a for a in data.get('artifacts',[]) if not a['expired']]
    if not artifacts:return {}
    blob=request(artifacts[0]['archive_download_url'],token)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:return json.loads(z.read('state.json'))

def send(text):
    body={'chat_id':OWNER_CHAT_ID,'text':text}
    response=json.loads(request('https://api.telegram.org/bot'+os.environ['TG_BOT_TOKEN']+'/sendMessage',payload=body,timeout=20))
    return bool(response.get('ok'))

def main():
    # Failure to restore durable state must not silently reset deduplication.
    state=restore()
    now=time.time()
    try:
        request(PAGES_URL)
        data=json.loads(request(API_URL+'/health/operations',os.environ['OPS_SECRET']))
        bad=data.get('status')!='ok'
    except Exception:bad=True
    previous=bool(state.get('open'))
    should_send=(bad and (not previous or now-state.get('last_sent',0)>86400)) or (not bad and previous)
    if should_send:
        text='МАЙТИМ: сайт, API, БД или недельное расписание недоступны. Проверьте Render и health-check. Время UTC: '+time.strftime('%Y-%m-%d %H:%M',time.gmtime(now)) if bad else 'МАЙТИМ: работа сервиса и расписания восстановлена.'
        try:
            if send(text):state.update(open=bad,last_sent=now)
        except Exception:
            # Unknown Telegram result: defer rather than flood on every five-minute run.
            state.update(open=bad,last_sent=now,delivery_unknown=True)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state))
    print('External checks:', 'degraded' if bad else 'ok')
if __name__=='__main__':main()
