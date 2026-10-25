from datetime import datetime
from django.test import TestCase
from myteam.clock import FrozenClock,MOSCOW
from myteam.models import Person,Enrollment,Member,Notification
from myteam.rounds import ensure_round
from myteam.matching import prepare
from myteam.jobs import publish
from myteam.contacts import send_contacts
class PrivacyTests(TestCase):
    def setUp(self):
        self.r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        self.people=[Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m',onboarding_done=True,chat_id=i+1,delivery_verified_at=self.r.closes_at) for i in range(3)]
        for p in self.people[:2]:Enrollment.objects.create(person=p,round=self.r)
        prepare(self.r.id,FrozenClock(self.r.prepares_at))
        self.meeting=self.r.meetings.get()
    def login(self,p):
        s=self.client.session;s['person_id']=str(p.id);s.save()
    def test_draft_and_foreign_meeting_are_private(self):
        self.login(self.people[0])
        url=f'/meetings/{self.meeting.id}/'
        self.assertEqual(self.client.get(url).status_code,404)
        publish(self.r.id,FrozenClock(self.r.starts_at))
        self.assertEqual(self.client.get(url).status_code,302)
        self.login(self.people[2]);self.assertEqual(self.client.get(url).status_code,404)
    def test_contacts_without_username_are_scoped_to_members(self):
        publish(self.r.id,FrozenClock(self.r.starts_at))
        self.assertFalse(send_contacts(3,3,self.meeting.id,7))
        self.assertTrue(send_contacts(1,1,self.meeting.id,8))
        text=Notification.objects.get(kind='contacts').text
        self.assertIn('tg://user?id=2',text)
        self.assertNotIn('id=3',text)
