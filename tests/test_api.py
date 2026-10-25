import json
from datetime import datetime,timedelta
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.contrib.sessions.backends.db import SessionStore
from myteam.models import Person,LoginAttempt,Enrollment,Member,Feedback,Achievement
from myteam.users import approve_login,confirm_login,digest
from myteam.clock import MOSCOW,FrozenClock
from myteam.rounds import ensure_round
from myteam.jobs import tick

@override_settings(TELEGRAM_BOT_USERNAME='isolated_bot',FRONTEND_ORIGINS=['https://pobazar.github.io'],CSRF_TRUSTED_ORIGINS=['https://pobazar.github.io'])
class DataApiTests(TestCase):
    origin='https://pobazar.github.io'
    def setUp(self):
        self.client=Client(enforce_csrf_checks=True)
        self.headers={'HTTP_ORIGIN':self.origin}
        result=self.client.get('/bridge/bootstrap/',**self.headers).json()
        self.token=result['session'];self.csrf=result['csrf_token'];self.client.cookies.clear()
    def call(self,path,data=None):
        headers={**self.headers,'HTTP_AUTHORIZATION':'Bearer '+self.token,'HTTP_X_CSRFTOKEN':self.csrf}
        r=self.client.get(path,**headers) if data is None else self.client.post(path,json.dumps(data),content_type='application/json',**headers)
        if 'X-Myteam-Session' in r:self.token=r['X-Myteam-Session']
        if r.headers.get('Content-Type','').startswith('application/json') and r.json().get('csrf_token'):self.csrf=r.json()['csrf_token']
        self.client.cookies.clear()
        return r
    def authenticate(self,complete=True,onboarded=True):
        p=Person.objects.create(telegram_id=71,full_name='Анна',team='Дизайн' if complete else '',city='Москва' if complete else '',city_key='moskva' if complete else '',onboarding_done=onboarded,chat_id=71,delivery_verified_at=datetime(2026,10,1,tzinfo=MOSCOW))
        s=SessionStore(self.token);s['person_id']=str(p.id);s.save()
        return p
    def test_guest_data_never_redirects_or_returns_html(self):
        for path in ('/api/activities/','/api/profile/','/api/history/'):
            r=self.call(path);self.assertEqual(r.status_code,401)
            self.assertEqual(r.json()['error'],'auth_required');self.assertNotIn('Location',r)
    def test_explicit_login_then_confirmation_rotates_session_and_skips_second_onboarding(self):
        old=self.token
        r=self.call('/api/login/',{});self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['code']),6)
        nonce=SessionStore(self.token)['login_token']
        approve_login(nonce,{'id':71,'first_name':'Анна'},71)
        self.assertEqual(self.call('/api/login/status/',{}).json()['state'],'waiting')
        attempt=LoginAttempt.objects.get(token_hash=digest(nonce));confirm_login(attempt.id,{'id':71},71)
        r=self.call('/api/login/status/',{})
        self.assertEqual(r.json()['state'],'needs_profile');self.assertNotEqual(old,self.token)
        self.assertTrue(Person.objects.get(telegram_id=71).onboarding_done)
        r=self.call('/api/profile/',{'full_name':'Анна Соколова','team':'Дизайн','city':'Москва'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['state'],'authenticated')
    def test_profile_requires_completion_and_returns_field_errors_without_html(self):
        p=self.authenticate(complete=False)
        self.assertEqual(self.call('/api/activities/').json()['state'],'needs_profile')
        self.assertEqual(self.call('/api/history/').status_code,409)
        r=self.call('/api/profile/',{'full_name':'','team':'Дизайн','city':'Москва'})
        self.assertEqual(r.status_code,422);self.assertIn('full_name',r.json()['fields'])
        self.assertNotIn('telegram_id',self.call('/api/profile/').json()['profile'])
    def test_existing_unfinished_onboarding_is_completed_explicitly(self):
        self.authenticate(onboarded=False)
        self.assertEqual(self.call('/api/activities/').json()['state'],'needs_onboarding')
        self.assertEqual(self.call('/api/onboarding/',{}).json()['state'],'authenticated')
    def test_logout_is_idempotent_json_and_revokes_the_old_token(self):
        self.authenticate()
        from django.contrib.sessions.models import Session
        old=self.token;before=Session.objects.count()
        r=self.call('/api/logout/',{})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json(),{'status':'logged_out'})
        self.assertNotIn('Location',r);self.assertFalse(SessionStore().exists(old))
        self.assertEqual(Session.objects.count(),before-1)
        self.assertEqual(self.call('/api/logout/',{}).status_code,200)
        self.assertEqual(self.call('/api/activities/').status_code,401)
    def test_logout_still_requires_csrf_for_an_active_session(self):
        self.authenticate()
        r=self.client.post('/api/logout/',data='{}',content_type='application/json',HTTP_AUTHORIZATION='Bearer '+self.token,HTTP_ORIGIN=self.origin)
        self.assertEqual(r.status_code,403);self.assertEqual(r.json()['error'],'csrf_failed')
        self.assertTrue(SessionStore().exists(self.token))
    def test_data_flow_enrollment_publication_feedback_history_and_privacy(self):
        p=self.authenticate();start=datetime(2026,10,28,9,tzinfo=MOSCOW)
        r=ensure_round(start)
        with patch('myteam.clock.Clock.now',return_value=r.closes_at-timedelta(days=1)):
            self.assertEqual(self.call('/api/activities/').json()['next']['enrollment_count'],0)
        other=Person.objects.create(telegram_id=72,full_name='Михаил',team='Разработка',city='Казань',city_key='kazan',onboarding_done=True)
        Enrollment.objects.create(person=other,round=r)
        cancelled=Person.objects.create(telegram_id=74)
        Enrollment.objects.create(person=cancelled,round=r,active=False)
        Enrollment.objects.create(person=cancelled,round=ensure_round(r.ends_at))
        with patch('myteam.clock.Clock.now',return_value=r.closes_at-timedelta(days=1)):
            self.assertEqual(self.call('/api/activities/').json()['next']['enrollment_count'],1)
            self.assertEqual(self.call(f'/api/rounds/{r.id}/enrollment/',{'action':'enroll'}).status_code,200)
            upcoming=self.call('/api/activities/').json()['next']
            self.assertTrue(upcoming['enrolled']);self.assertEqual(upcoming['enrollment_count'],2)
            self.call(f'/api/rounds/{r.id}/enrollment/',{'action':'cancel'})
            self.assertEqual(self.call('/api/activities/').json()['next']['enrollment_count'],1)
            self.call(f'/api/rounds/{r.id}/enrollment/',{'action':'enroll'})
        tick(FrozenClock(r.prepares_at));tick(FrozenClock(start))
        with patch('myteam.clock.Clock.now',return_value=start):
            data=self.call('/api/activities/').json();self.assertEqual(data['current']['kind'],'active')
            self.assertEqual(len(data['current']['participants']),2)
            self.assertNotIn('telegram_id',data['current']['participants'][0])
            meeting=data['current']['meeting_id']
            self.assertEqual(self.call(f'/api/meetings/{meeting}/feedback/',{'outcome':'yes','rating':4}).status_code,200)
            self.assertEqual(self.call('/api/activities/').json()['current']['kind'],'completed')
            award=self.call('/api/profile/').json()['achievements'][0]
            self.assertEqual(award['key'],'first_coffee')
            self.assertEqual(datetime.fromisoformat(award['earned_at'].replace('Z','+00:00')),Achievement.objects.get(person=p,key='first_coffee').created_at)
        with patch('myteam.clock.Clock.now',return_value=r.ends_at):
            entries=self.call('/api/history/').json()['entries'];self.assertEqual(len(entries),1)
            self.assertEqual(entries[0]['answer']['rating'],4);self.assertFalse(entries[0]['can_rate'])
        self.assertFalse(Enrollment.objects.filter(person=p).exclude(round=r).exists())
        third=Person.objects.create(telegram_id=73,full_name='Другой',team='Т',city='М',city_key='m',onboarding_done=True)
        s=SessionStore(self.token);s['person_id']=str(third.id);s.save()
        self.assertEqual(self.call(f'/api/meetings/{meeting}/feedback/').status_code,404)
    def test_no_feedback_without_reason_is_saved_as_final(self):
        p=self.authenticate();r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        other=Person.objects.create(telegram_id=72,full_name='Михаил',team='Разработка',city='Казань',city_key='kazan')
        for person in (p,other):Enrollment.objects.create(person=person,round=r)
        tick(FrozenClock(r.prepares_at));tick(FrozenClock(r.starts_at))
        meeting=Member.objects.get(person=p,round=r).meeting_id
        with patch('myteam.clock.Clock.now',return_value=r.starts_at):
            response=self.call(f'/api/meetings/{meeting}/feedback/',{'outcome':'no','comment':''})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()['answer']['final'])
            self.assertIsNone(response.json()['answer']['rating'])
            self.assertEqual(Feedback.objects.get(member__person=p).comment,'')
            self.assertEqual(self.call('/api/activities/').json()['current']['kind'],'completed')
        self.assertFalse(Achievement.objects.filter(person=p).exists())
    def test_unauthenticated_data_read_does_not_create_anonymous_sessions(self):
        from django.contrib.sessions.models import Session
        before=Session.objects.count()
        response=Client().get('/api/activities/',HTTP_ORIGIN=self.origin)
        self.assertEqual(response.status_code,401)
        self.assertEqual(Session.objects.count(),before)
    def test_unknown_api_path_and_wrong_method_are_json_not_html(self):
        response=self.call('/api/unknown/')
        self.assertEqual(response.status_code,404);self.assertEqual(response.json()['error'],'not_found')
        response=self.call('/api/logout/')
        self.assertEqual(response.status_code,405);self.assertEqual(response.json()['error'],'method_not_allowed')
        self.assertIn('POST',response['Allow'])

    def test_coffee_roles_contacts_boundary_and_immutable_feedback(self):
        p=self.authenticate()
        start=datetime(2026,10,28,9,tzinfo=MOSCOW)
        r=ensure_round(start)
        people=[p]+[Person.objects.create(telegram_id=i,full_name=f'Участник {i}',team='Разработка',city='Москва',city_key='moskva',onboarding_done=True) for i in (72,73)]
        for person in people:Enrollment.objects.create(person=person,round=r)
        tick(FrozenClock(r.prepares_at));tick(FrozenClock(start))
        with patch('myteam.clock.Clock.now',return_value=start):
            current=self.call('/api/activities/').json()['current']
            self.assertEqual(current['kind'],'active')
            self.assertEqual(sum(x['is_organizer'] for x in current['participants']),1)
            self.assertEqual(sum(bool(x['contacts_url']) for x in current['participants']),2)
            self.assertIn('офлайн',current['instructions'])
            self.assertIn('попутешествовать',current['instructions'])
            self.assertNotIn('telegram_id',str(current))
        boundary=r.ends_at-timedelta(hours=12)
        with patch('myteam.clock.Clock.now',return_value=boundary-timedelta(seconds=1)):
            self.assertEqual(self.call('/api/activities/').json()['current']['kind'],'active')
        with patch('myteam.clock.Clock.now',return_value=boundary):
            self.assertEqual(self.call('/api/activities/').json()['current']['kind'],'upcoming')
            self.assertEqual(len(self.call('/api/history/').json()['entries']),1)
        m=Member.objects.get(person=p,round=r)
        path=f'/api/meetings/{m.meeting_id}/feedback/'
        with patch('myteam.clock.Clock.now',return_value=r.ends_at+timedelta(days=365)):
            data={'outcome':'yes','rating':5,'comment':'Спасибо'}
            self.assertEqual(self.call(path,data).status_code,200)
            self.assertTrue(self.call(path).json()['readonly'])
            self.assertEqual(self.call(path,data).status_code,200)
            self.assertEqual(self.call(path,{'outcome':'no'}).status_code,409)
        self.assertEqual(Feedback.objects.get(member=m).revision,1)
