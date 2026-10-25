from datetime import datetime,timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Person,Enrollment,Member,Notification,Round
from myteam.rounds import ensure_round
from myteam.matching import prepare
from myteam.jobs import publish
from myteam.scheduled_events import execute,target_start,notification_kinds,window
from myteam.notifications import drain

class ScheduledEventTests(TestCase):
    def setUp(self):
        self.r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        self.people=[Person.objects.create(telegram_id=i,chat_id=i,full_name=f'Участник {i}',team='ИТ',city='Москва',city_key='moskva',onboarding_done=True,delivery_verified_at=self.r.closes_at) for i in (1,2)]
        for person in self.people:Enrollment.objects.create(round=self.r,person=person)
    def test_delayed_prepare_does_not_request_feedback_or_publish(self):
        old=ensure_round(self.r.starts_at-timedelta(days=7))
        for person in self.people:Enrollment.objects.create(round=old,person=person)
        prepare(old.id,FrozenClock(old.prepares_at));publish(old.id,FrozenClock(old.starts_at))
        Notification.objects.all().delete()
        instant=self.r.starts_at  # Preparation has been delayed until publication time.
        result=execute('prepare',FrozenClock(instant))
        self.assertFalse(result.error);self.r.refresh_from_db()
        self.assertIsNotNone(self.r.prepared_at);self.assertIsNone(self.r.published_at)
        self.assertFalse(Notification.objects.filter(kind__in=('meeting','feedback_first','signup_invite')).exists())
        ids=set(Member.objects.filter(round=self.r).values_list('id',flat=True))
        execute('prepare',FrozenClock(instant))
        self.assertEqual(ids,set(Member.objects.filter(round=self.r).values_list('id',flat=True)))
    def test_publish_recovers_absent_draft_when_prepare_action_was_missed(self):
        clock=FrozenClock(self.r.starts_at)
        self.assertFalse(execute('publish',clock).error)
        self.r.refresh_from_db();self.assertIsNotNone(self.r.published_at)
        count=Notification.objects.filter(kind='meeting').count()
        execute('publish',clock);self.assertEqual(Notification.objects.filter(kind='meeting').count(),count)
    def test_other_round_failure_does_not_block_invites(self):
        self.r.preparation_error='isolated_other_stage_error';self.r.save()
        game=ensure_round(self.r.ends_at)
        instant=game.starts_at-timedelta(days=6)
        result=execute('invite',FrozenClock(instant))
        self.assertFalse(result.error);self.assertEqual(result.round.id,game.id)
        self.assertEqual(Notification.objects.filter(kind='signup_invite',round=game).count(),2)
        self.assertFalse(Notification.objects.filter(kind__in=('feedback_first','meeting')).exists())
    def test_queue_and_expired_leases_are_scoped_by_event_and_round(self):
        now=self.r.starts_at+timedelta(days=1)
        game=ensure_round(self.r.ends_at)
        Notification.objects.create(key='foreign-event',kind='meeting',round=game,chat_id=1,text='foreign')
        Notification.objects.create(key='foreign-round',kind='signup_invite',round=self.r,chat_id=1,text='foreign')
        Notification.objects.create(key='foreign-lease',kind='meeting',round=game,chat_id=1,text='foreign',status='sending',leased_until=now-timedelta(minutes=1))
        execute('invite',FrozenClock(now))
        sent=[]
        drain(FrozenClock(now),lambda *args:sent.append(args) or 1,force=True,kinds=notification_kinds('invite'),round_id=game.id)
        self.assertEqual(len(sent),2)
        self.assertEqual(Notification.objects.get(key='foreign-event').status,'pending')
        self.assertEqual(Notification.objects.get(key='foreign-round').status,'pending')
        self.assertEqual(Notification.objects.get(key='foreign-lease').status,'sending')
    def test_window_boundaries_and_manual_date_cannot_override_clock(self):
        for event in ('prepare','publish','feedback','invite'):
            due,expiry=window(event,self.r.starts_at)
            self.assertEqual(target_start(event,due),self.r.starts_at)
            before_count=Round.objects.count()
            result=execute(event,FrozenClock(due-timedelta(microseconds=1)),'2026-10-28')
            self.assertIsNone(result.round);self.assertEqual(result.status,'outside_window')
            self.assertEqual(Round.objects.count(),before_count)
            result=execute(event,FrozenClock(expiry),'2026-10-28')
            if event=='publish':self.assertEqual(result.status,'cancelled')
            else:self.assertIsNone(result.round)
        for value in ('2026-10-27','2026-2-04','not-a-date'):
            with self.assertRaises(ValueError):target_start('invite',self.r.starts_at,value)
    def test_paused_publication_preserves_manual_draft(self):
        prepare(self.r.id,FrozenClock(self.r.prepares_at))
        self.r.refresh_from_db();self.r.publication_paused=True;self.r.save()
        ids=set(Member.objects.values_list('id',flat=True))
        result=execute('publish',FrozenClock(self.r.starts_at))
        self.assertEqual(result.status,'paused');self.assertFalse(result.error)
        self.r.refresh_from_db();self.assertIsNone(self.r.published_at)
        self.assertEqual(ids,set(Member.objects.values_list('id',flat=True)))
        self.assertFalse(Notification.objects.filter(kind='meeting').exists())

    def test_housekeeping_finishes_history_without_sending_other_events(self):
        old=ensure_round(self.r.starts_at-timedelta(days=14))
        old.state='published';old.published_at=old.starts_at;old.save()
        stale=ensure_round(self.r.starts_at-timedelta(days=21));stale.state='closed';stale.save()
        execute('prepare',FrozenClock(self.r.prepares_at))
        # The older published round's persisted end has elapsed; no history rows are removed.
        old.refresh_from_db();stale.refresh_from_db()
        self.assertEqual(old.state,'completed');self.assertEqual(stale.state,'expired')
        self.assertFalse(Notification.objects.exists())
