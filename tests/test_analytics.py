from datetime import datetime
from django.test import TestCase
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Person,Enrollment,AnalyticsEvent,Feedback
from myteam.rounds import ensure_round,enroll
from myteam.matching import prepare
from myteam.jobs import publish
from myteam.feedback import save_feedback
class AnalyticsTests(TestCase):
    def test_retries_do_not_duplicate_and_revisions_survive(self):
        r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        for i in range(2):
            p=Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m',chat_id=i+1,delivery_verified_at=r.closes_at)
            enroll(p.id,r.id,True,FrozenClock(r.closes_at.replace(hour=17)))
            enroll(p.id,r.id,True,FrozenClock(r.closes_at.replace(hour=17)))
        self.assertEqual(AnalyticsEvent.objects.filter(kind='enrolled').count(),2)
        prepare(r.id,FrozenClock(r.prepares_at));publish(r.id,FrozenClock(r.starts_at));publish(r.id,FrozenClock(r.starts_at))
        self.assertEqual(AnalyticsEvent.objects.filter(kind='participation').count(),2)
        meeting=r.meetings.get()
        Feedback.objects.create(member=meeting.members.get(person=p),outcome='pending')
        for data in ({'outcome':'yes','rating':5},{'outcome':'yes','rating':5}):
            save_feedback(p.id,meeting.id,data,FrozenClock(r.starts_at))
        self.assertEqual(AnalyticsEvent.objects.filter(kind='feedback').count(),2)
        self.assertEqual(AnalyticsEvent.objects.filter(kind='achievement_awarded').count(),1)
        self.assertEqual(AnalyticsEvent.objects.filter(kind='achievement_revoked').count(),0)
