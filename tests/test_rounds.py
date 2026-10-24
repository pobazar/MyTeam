from datetime import datetime,timedelta
from django.test import TestCase
from myteam.clock import FrozenClock,MOSCOW
from myteam.models import Person,Enrollment
from myteam.rounds import ensure_round,enroll,RuleError
class RoundTests(TestCase):
    def setUp(self):
        self.r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        self.assertEqual(self.r.prepares_at,self.r.closes_at)
        self.p=Person.objects.create(telegram_id=1,first_name='А',last_name='Б',team='Команда',city='Москва',city_key='moskva',chat_id=1,delivery_verified_at=self.r.closes_at)
    def test_boundary_idempotency_and_no_automatic_enrollment(self):
        clock=FrozenClock(self.r.closes_at-timedelta(microseconds=1))
        enroll(self.p.id,self.r.id,False,clock)
        self.assertEqual(Enrollment.objects.count(),0)
        for _ in range(2):enroll(self.p.id,self.r.id,True,clock)
        self.assertEqual(Enrollment.objects.count(),1)
        enroll(self.p.id,self.r.id,False,clock)
        enroll(self.p.id,self.r.id,True,clock)
        self.assertEqual(Enrollment.objects.get().revision,3)
        with self.assertRaises(RuleError):enroll(self.p.id,self.r.id,False,FrozenClock(self.r.closes_at))
        next_round=ensure_round(self.r.starts_at+timedelta(days=7))
        self.assertFalse(Enrollment.objects.filter(round=next_round).exists())
    def test_incomplete_profile_cannot_enroll(self):
        self.p.last_name='';self.p.save()
        with self.assertRaises(RuleError):enroll(self.p.id,self.r.id,True,FrozenClock(self.r.closes_at-timedelta(days=1)))

    def test_closed_signup_still_shows_existing_registration(self):
        from unittest.mock import patch
        self.p.onboarding_done=True;self.p.save()
        enroll(self.p.id,self.r.id,True,FrozenClock(self.r.closes_at-timedelta(days=1)))
        session=self.client.session;session['person_id']=str(self.p.id);session.save()
        with patch('myteam.views.Clock.now',return_value=self.r.closes_at):
            response=self.client.get('/')
        self.assertContains(response,'Запись закрыта.')
        self.assertContains(response,'Ты записан.')
        self.assertNotContains(response,'Отменить запись')
