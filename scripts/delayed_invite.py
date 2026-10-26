"""One-off timer; dispatches the existing main workflow, never sends Telegram directly."""
import json
import os
import time
import urllib.request
from datetime import datetime,timezone,timedelta

REPOSITORY='pobazar/MyTeam'
ENDPOINT=f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/schedule.yml/dispatches'


def target_time(event,round_date,invite_at,now):
    if event!='invite':raise ValueError('Only invitation dispatch is supported')
    day=datetime.strptime(round_date,'%Y-%m-%d').date()
    if day.isoformat()!=round_date or day.weekday()!=2:raise ValueError('Expected a Wednesday round date')
    target=datetime.fromisoformat(invite_at.replace('Z','+00:00'))
    if target.tzinfo is None:raise ValueError('Explicit timezone required')
    target=target.astimezone(timezone.utc)
    if not -timedelta(minutes=5)<=target-now<=timedelta(hours=1):
        raise ValueError('Requested time must be within one hour; late limit is five minutes')
    # Same invitation window as the backend: preceding Thursday 09 MSK to Tue 21 MSK.
    start=datetime(day.year,day.month,day.day,6,tzinfo=timezone.utc)
    if not start-timedelta(days=6)<=target<start-timedelta(hours=12):
        raise ValueError('Requested time is outside the round invitation window')
    return target


def main():
    if os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY:
        raise ValueError('This timer is restricted to MyTeam')
    round_date=os.environ['MYTEAM_ROUND_DATE']
    target=target_time(os.environ['MYTEAM_EVENT'],round_date,os.environ['MYTEAM_INVITE_AT'],datetime.now(timezone.utc))
    print('Waiting to dispatch invite for round',round_date,'at',target.isoformat(),flush=True)
    while (remaining:=(target-datetime.now(timezone.utc)).total_seconds())>0:
        time.sleep(min(30,remaining))
    if datetime.now(timezone.utc)-target>timedelta(minutes=5):
        raise ValueError('Timer resumed too late; no dispatch performed')
    # No credentials in arguments/logs. Only the normal main workflow receives the event;
    # its OIDC identity, live recipient selection, outbox and dedup remain authoritative.
    data=json.dumps({'ref':'main','inputs':{'event':'invite','round_date':round_date}}).encode()
    request=urllib.request.Request(ENDPOINT,data=data,headers={
        'Authorization':'Bearer '+os.environ['GH_TOKEN'],
        'Accept':'application/vnd.github+json','Content-Type':'application/json',
        'X-GitHub-Api-Version':'2022-11-28'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
        if response.status!=204:raise ValueError('Unexpected dispatch response')
    print('Normal main invite workflow dispatched. Check its delivery result separately.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Never emit credential-bearing HTTP bodies or request details.
        print('Delayed invite failed:',type(error).__name__,flush=True)
        raise SystemExit(1)
