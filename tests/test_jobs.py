from datetime import datetime,timedelta
from django.test import TestCase
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Round,Person,Enrollment,Member,Notification
from myteam.rounds import ensure_round
from myteam.jobs import tick
class JobTests(TestCase):
    def test_two_cycles_restart_and_pause(self):
        r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        for i in range(3):
            p=Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m',chat_id=i+1,delivery_verified_at=r.closes_at)
            Enrollment.objects.create(person=p,round=r)
        for instant in (r.closes_at,r.prepares_at,r.prepares_at):tick(FrozenClock(instant))
        ids=set(Member.objects.values_list('id',flat=True))
        r.refresh_from_db();r.publication_paused=True;r.save()
        tick(FrozenClock(r.starts_at));r.refresh_from_db();self.assertIsNone(r.published_at)
        r.publication_paused=False;r.save()
        tick(FrozenClock(r.starts_at));tick(FrozenClock(r.starts_at))
        r.refresh_from_db();self.assertEqual(r.state,'published')
        self.assertEqual(Member.objects.count(),3)
        self.assertEqual(Notification.objects.filter(kind='meeting').count(),3)
        self.assertEqual(ids,set(Member.objects.values_list('id',flat=True)))
        next_round=Round.objects.get(starts_at=r.ends_at)
        self.assertFalse(Enrollment.objects.filter(round=next_round).exists())
        for instant in (next_round.prepares_at,next_round.starts_at):tick(FrozenClock(instant))
        next_round.refresh_from_db();self.assertEqual(next_round.state,'published')
        self.assertEqual(Member.objects.filter(round=next_round).count(),0)
    def test_corrupt_draft_cannot_publish(self):
        r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        for i in range(2):
            p=Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m')
            Enrollment.objects.create(person=p,round=r)
        tick(FrozenClock(r.prepares_at));Member.objects.first().delete()
        tick(FrozenClock(r.starts_at));r.refresh_from_db()
        self.assertIsNone(r.published_at)
        self.assertFalse(Notification.objects.filter(kind='meeting').exists())
    def test_long_outage_expires_without_stale_invites(self):
        r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        tick(FrozenClock(r.ends_at+timedelta(days=3)))
        r.refresh_from_db();self.assertEqual(r.state,'expired')
        self.assertEqual(Notification.objects.count(),0)

    def test_failed_write_rolls_back_draft_and_can_recover(self):
        from unittest.mock import patch
        from django.db import DatabaseError
        from myteam.models import Incident
        r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        for i in range(2):
            p=Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m')
            Enrollment.objects.create(person=p,round=r)
        with patch('myteam.matching.Meeting.objects.create',side_effect=DatabaseError('simulated exhausted storage')):
            tick(FrozenClock(r.prepares_at))
        r.refresh_from_db();self.assertIsNone(r.prepared_at)
        self.assertFalse(Member.objects.filter(round=r).exists())
        self.assertEqual(Incident.objects.filter(resolved_at__isnull=True).count(),1)
        tick(FrozenClock(r.prepares_at));r.refresh_from_db()
        self.assertIsNotNone(r.prepared_at)
        self.assertEqual(Member.objects.filter(round=r).count(),2)
        self.assertEqual(Incident.objects.filter(resolved_at__isnull=False).count(),1)
