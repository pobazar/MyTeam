from datetime import datetime,timedelta
from django.test import TestCase
from myteam.clock import FrozenClock,MOSCOW
from myteam.invitations import invitation_window,schedule_invites
from myteam.models import Person,Enrollment,Notification,Job
from myteam.notifications import drain,enqueue
from myteam.rounds import ensure_round
from myteam.jobs import tick

class InvitationTests(TestCase):
    def setUp(self):
        self.r=ensure_round(datetime(2026,11,4,9,tzinfo=MOSCOW))
        self.due,self.expiry=invitation_window(self.r)
        self.people=[]
        for i in range(6):
            self.people.append(Person.objects.create(telegram_id=i+1,chat_id=i+1,first_name='Имя',last_name='Фамилия',team='Команда',city='Москва',city_key='moskva',onboarding_done=True,delivery_verified_at=self.due))
        Enrollment.objects.create(person=self.people[0],round=self.r)
        Enrollment.objects.create(person=self.people[1],round=self.r,active=False)
        self.people[2].delivery_blocked=True;self.people[2].save()
        self.people[3].delivery_verified_at=None;self.people[3].save()
        self.people[4].onboarding_done=False;self.people[4].save()
    def test_thursday_only_once_and_skip_enrolled_or_unreachable(self):
        self.assertEqual((self.due.weekday(),self.due.hour),(3,9))
        schedule_invites(self.r,FrozenClock(self.due-timedelta(microseconds=1)))
        self.assertEqual(Notification.objects.count(),0)
        tick(FrozenClock(self.due));tick(FrozenClock(self.due))
        self.assertSetEqual(set(Notification.objects.filter(kind='signup_invite').values_list('person_id',flat=True)),{self.people[1].id,self.people[5].id})
        self.assertEqual(Job.objects.filter(key=f'signup_invite:{self.r.id}').count(),1)
        self.assertEqual(Enrollment.objects.count(),2)
    def test_new_enrollment_and_block_suppress_queued_invite(self):
        schedule_invites(self.r,FrozenClock(self.due))
        Enrollment.objects.filter(person=self.people[1],round=self.r).update(active=True)
        self.people[5].delivery_blocked=True;self.people[5].save()
        sent=[]
        drain(FrozenClock(self.due),transport=lambda *a:sent.append(a) or 1,force=True)
        self.assertEqual(sent,[])
        self.assertEqual(Notification.objects.filter(status='cancelled').count(),2)
    def test_no_stale_invitation_after_outage(self):
        schedule_invites(self.r,FrozenClock(self.expiry))
        self.assertFalse(Notification.objects.exists())
        schedule_invites(self.r,FrozenClock(self.due))
        sent=[]
        drain(FrozenClock(self.expiry),transport=lambda *a:sent.append(a) or 1,force=True)
        self.assertEqual(sent,[])
    def test_old_last_reminder_is_never_delivered(self):
        p=self.people[0]
        n=enqueue('legacy-reminder','feedback_last',p.chat_id,'legacy',p,self.r,self.due)
        drain(FrozenClock(self.due),transport=lambda *a:self.fail('Old reminder must not be sent'),force=True)
        n.refresh_from_db();self.assertEqual(n.status,'cancelled')
