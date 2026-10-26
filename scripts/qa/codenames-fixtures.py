"""Build review JSON through real Django views, in a disposable local-only PostgreSQL DB."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timedelta
from urllib.parse import urlsplit
from unittest.mock import patch
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
if urlsplit(os.environ.get('DATABASE_URL','')).hostname not in ('127.0.0.1','localhost'):
    raise SystemExit('Use an explicit isolated local DATABASE_URL.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from django.test.utils import setup_databases,teardown_databases
from django.test import Client
from django.contrib.sessions.backends.db import SessionStore
from myteam.clock import MOSCOW,FrozenClock
from myteam.rounds import ensure_round
from myteam.models import Person,Enrollment,Member,Achievement,Notification
from myteam.scheduled_events import execute
from myteam.feedback import save_feedback
from myteam.activities.codenames import CodeNames,GAME_URL
settings.SEND_TELEGRAM=False
settings.DATABASES['default']['TEST']['NAME']='myteam_codenames_preview'
db=setup_databases(verbosity=0,interactive=False)
result={}
names=['Анна Соколова','Михаил Орлов','Елена Волкова','Илья Морозов','Мария Кузнецова','Алексей Смирнов','Ольга Павлова']
teams=['Дизайн','Разработка','Поддержка','Маркетинг']
def get(client,path,headers,now):
    with patch('myteam.clock.Clock.now',return_value=now):response=client.get(path,**headers)
    assert response.status_code==200
    body=response.json();body.pop('csrf_token',None);client.cookies.clear();return body
try:
    for index,count in enumerate((4,5,7)):
        start=datetime(2026,11,4,9,tzinfo=MOSCOW)+timedelta(weeks=index*2)
        r=ensure_round(start);r.activity='code_names';r.rules_version=1;r.publication_paused=False;r.save()
        people=[]
        for i in range(count):
            p=Person.objects.create(telegram_id=9000000+index*100+i,chat_id=9000000+index*100+i,full_name=names[i],team=teams[i%4],city='Москва' if i%2==0 else 'Казань',city_key='moskva' if i%2==0 else 'kazan',username=f'myteam_qa_{index}_{i}',onboarding_done=True,delivery_verified_at=start)
            Enrollment.objects.create(person=p,round=r);people.append(p)
        assert not execute('publish',FrozenClock(start)).error
        meeting=r.meetings.get();organizer=meeting.activity_data['organizer_person_id']
        person=next(p for p in people if (str(p.id)==organizer if count==4 else str(p.id)!=organizer))
        session=SessionStore();session['person_id']=str(person.id);session.create()
        headers={'HTTP_AUTHORIZATION':'Bearer '+session.session_key};client=Client()
        result[f'group{count}']=get(client,'/api/activities/',headers,start)
        if count==4:
            result['feedback']=get(client,f'/api/meetings/{meeting.id}/feedback/',headers,start)
            result['notification']=Notification.objects.get(kind='meeting',round=r,person=person).text
            result['notification_buttons']=Notification.objects.get(kind='meeting',round=r,person=person).payload
            answer=save_feedback(person.id,meeting.id,{'outcome':'yes','rating':5,'comment':'Было интересно услышать, какие разные ассоциации возникают у коллег.'},FrozenClock(start+timedelta(days=2)))
            Achievement.objects.create(person=person,key='first_coffee',created_at=start-timedelta(days=14))
            result['saved_answer']={'outcome':answer.outcome,'rating':answer.rating,'final':True}
            result['profile']=get(client,'/api/profile/',headers,start+timedelta(days=2))
            result['completed']=get(client,'/api/activities/',headers,start+timedelta(days=2))
            result['history']=get(client,'/api/history/',headers,r.ends_at)
    Path('/tmp/myteam-codenames-preview.json').write_text(json.dumps(result,ensure_ascii=False,default=str))
    out=root/'docs/qa/code-names';out.mkdir(parents=True,exist_ok=True)
    (out/'instructions.txt').write_text('Code Names\n\n'+CodeNames().instructions(False)+'\n\nОткрыть игру: '+GAME_URL+'\n')
    print('Built backend-derived fixtures: groups of 4, 5 and 7; game feedback, award, completed state and history. No production writes or Telegram sends.')
finally:teardown_databases(db,verbosity=0)
