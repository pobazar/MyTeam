import json
from datetime import datetime,timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Person,Enrollment,Notification
from myteam.rounds import ensure_round,enroll
from myteam.user_messages import invitation
from myteam.notifications import eligible

@override_settings(TELEGRAM_WEBHOOK_SECRET='isolated-only')
class TelegramEnrollmentTests(TestCase):
    def setUp(self):
        self.r=ensure_round(datetime(2026,11,4,9,tzinfo=MOSCOW))
        self.now=self.r.closes_at-timedelta(days=4)
        self.p=Person.objects.create(telegram_id=71,chat_id=71,full_name='Анна',team='Дизайн',city='Москва',city_key='moskva',onboarding_done=True,delivery_verified_at=self.now)
        text,payload=invitation(self.r)
        self.n=Notification.objects.create(key='test-invite',kind='signup_invite',chat_id=71,person=self.p,round=self.r,text=text,payload=payload,status='sent',telegram_message_id=123)
    def click(self,action,update=1,sender=71,message_id=123,data=None):
        body={'update_id':update,'callback_query':{'id':f'callback-{update}','from':{'id':sender},'message':{'chat':{'id':sender,'type':'private'},'message_id':message_id},'data':data or f'enroll:{self.r.id}:{action}'}}
        with patch('myteam.clock.Clock.now',return_value=self.now),patch('myteam.telegram_enrollment.call',return_value={}) as transport,self.captureOnCommitCallbacks(execute=True):
            response=self.client.post('/telegram/webhook/',json.dumps(body),content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='isolated-only')
        self.assertEqual(response.status_code,200)
        return transport.call_args_list
    def test_buttons_share_web_state_and_duplicate_update_is_safe(self):
        calls=self.click('yes')
        e=Enrollment.objects.get(person=self.p,round=self.r)
        self.assertTrue(e.active);self.assertEqual(e.revision,1)
        self.assertIn('Ты записан.',str(calls))
        self.assertEqual(self.click('yes'),[])
        self.click('yes',update=2);e.refresh_from_db();self.assertEqual(e.revision,1)
        # The web API uses the same service; cancelling here must be reflected in Telegram.
        enroll(self.p.id,self.r.id,False,FrozenClock(self.now))
        calls=self.click('no',update=3);e.refresh_from_db()
        self.assertFalse(e.active);self.assertEqual(e.revision,2)
        self.assertIn('Ты не участвуешь.',str(calls))
        self.click('yes',update=4);e.refresh_from_db();self.assertTrue(e.active)
    def test_refusal_without_registration_does_not_enroll_or_create_row(self):
        self.click('no');self.assertFalse(Enrollment.objects.exists())
    def test_other_user_other_message_and_malformed_callbacks_cannot_enroll(self):
        self.click('yes',sender=72)
        self.click('yes',update=2,message_id=456)
        self.click('yes',update=3,data='enroll:broken:yes')
        self.assertFalse(Enrollment.objects.exists())
    def test_closed_registration_preserves_state_and_removes_buttons(self):
        self.click('yes')
        self.now=self.r.closes_at
        calls=self.click('no',update=2)
        self.assertTrue(Enrollment.objects.get().active)
        self.assertIn('Запись закрыта',str(calls))
        edit=next(c.args[1] for c in calls if c.args[0]=='editMessageText')
        self.assertEqual(edit['reply_markup']['inline_keyboard'],[])
    def test_incomplete_profile_uses_same_rejection_as_web(self):
        self.p.team='';self.p.save()
        calls=self.click('yes')
        self.assertFalse(Enrollment.objects.exists());self.assertIn('Заполните профиль',str(calls))
    def test_retired_contact_links_and_queued_messages_send_nothing(self):
        with patch('myteam.telegram.call') as transport:
            for i,prefix in enumerate(('c_','m_'),10):
                body={'update_id':i,'message':{'text':'/start '+prefix+str(self.r.id),'from':{'id':71},'chat':{'id':71,'type':'private'}}}
                self.assertEqual(self.client.post('/telegram/webhook/',json.dumps(body),content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='isolated-only').status_code,200)
            transport.assert_not_called()
        self.n.kind='contacts';self.assertFalse(eligible(self.n,self.now))
