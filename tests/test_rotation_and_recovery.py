import random
from collections import Counter
from datetime import datetime,timedelta
from unittest.mock import patch
from django.db import DatabaseError
from django.test import TestCase
from myteam.activities import ACTIVITIES
from myteam.activities.coffee import RandomCoffee
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Round,Person,Enrollment,Member,Meeting,Feedback,Notification
from myteam.rounds import ensure_round,ensure_calendar,enroll,RuleError
from myteam.rotation import choose,ready
from myteam.scheduled_events import execute,notification_kinds
from myteam.notifications import drain
from myteam.matching import prepare
from myteam.read_models import dashboard_context

class RotationTests(TestCase):
    start=datetime(2027,3,3,9,tzinfo=MOSCOW)
    def catalog(self):
        result={}
        for key in ('a','b','c'):
            a=RandomCoffee();a.key=key;a.title=key.upper();result[key]=a
        return result
    def round(self,start,key):
        return Round.objects.create(starts_at=start,ends_at=start+timedelta(weeks=1),closes_at=start-timedelta(hours=12),prepares_at=start-timedelta(hours=12),activity=key,state='published',published_at=start)
    def test_choice_is_frozen_and_does_not_end_when_every_format_has_been_used(self):
        with patch.dict(ACTIVITIES,self.catalog(),clear=True):
            for i,key in enumerate(('a','b','c'),1):self.round(self.start-timedelta(weeks=i),key)
            r=ensure_round(self.start)
            self.assertNotEqual(r.activity,'a');self.assertEqual(r.selection['source'],'rotation')
            frozen=r.selection.copy()
            with patch('myteam.rotation.choose',side_effect=AssertionError('must not redraw')):
                self.assertEqual(ensure_round(self.start).id,r.id)
            r.refresh_from_db();self.assertEqual(r.selection,frozen)
    def test_ratings_bias_random_choices_without_fixed_order_or_starvation(self):
        with patch.dict(ACTIVITIES,self.catalog(),clear=True):
            person=Person.objects.create(telegram_id=1)
            for weeks,key,rating in ((1,'a',3),(2,'b',5),(3,'c',1)):
                r=self.round(self.start-timedelta(weeks=weeks),key)
                meeting=Meeting.objects.create(round=r)
                # Multiple verified outcomes rather than weighting a single outlier.
                for i in range(30):
                    p=Person.objects.create(telegram_id=weeks*100+i)
                    m=Member.objects.create(round=r,meeting=meeting,person=p)
                    Feedback.objects.create(member=m,outcome='yes',rating=rating)
            rng=random.Random(24)
            counts=Counter(choose(self.start,rng)[0].key for _ in range(500))
            self.assertEqual(counts['a'],0);self.assertGreater(counts['b'],counts['c']*2);self.assertGreater(counts['c'],20)
            # Once a format has not appeared for the maximum wait, it must reappear.
            Round.objects.filter(activity='c').update(starts_at=self.start-timedelta(weeks=20))
            self.assertEqual(choose(self.start,random.Random(1))[0].key,'c')
    def test_unready_excluded_and_empty_catalog_recovers_without_recreating_round(self):
        self.assertTrue(ready('code_names',1))
        with patch.dict(ACTIVITIES,{},clear=True):
            r=ensure_round(self.start);self.assertEqual(r.activity,'unavailable')
        recovered=ensure_round(self.start)
        self.assertEqual(recovered.id,r.id);self.assertTrue(ready(recovered.activity,recovered.rules_version))
    def test_explicit_code_names_plan_is_preserved_and_next_round_uses_ready_alternative(self):
        r=ensure_round(datetime(2026,11,4,9,tzinfo=MOSCOW))
        self.assertEqual(r.activity,'code_names');self.assertEqual(r.selection['source'],'plan')
        later=ensure_round(datetime(2026,11,11,9,tzinfo=MOSCOW))
        self.assertNotEqual(later.activity,'code_names')
        self.assertTrue(ready(later.activity,later.rules_version))

class RecoveryTests(TestCase):
    def setUp(self):
        self.start=datetime(2026,10,28,9,tzinfo=MOSCOW);self.r=ensure_round(self.start)
        self.people=[Person.objects.create(telegram_id=i,chat_id=i,full_name=f'Участник {i}',team='ИТ',city='Москва',city_key='moskva',onboarding_done=True,delivery_verified_at=self.start) for i in (1,2)]
        for p in self.people:Enrollment.objects.create(person=p,round=self.r)
    def publish(self,at=None):return execute('publish',FrozenClock(at or self.start),self.start.date().isoformat())
    def test_missing_action_recovers_and_next_signup_exists(self):
        result=self.publish();self.assertFalse(result.error)
        self.r.refresh_from_db();self.assertIsNotNone(self.r.published_at)
        next_round=Round.objects.get(starts_at=self.r.ends_at)
        self.assertEqual(next_round.activity,'code_names');self.assertFalse(next_round.enrollments.exists())
        self.publish(self.start+timedelta(minutes=30))
        self.assertEqual(Member.objects.filter(round=self.r).count(),2)
        self.assertEqual(Notification.objects.filter(kind='meeting').count(),2)
    def test_complete_draft_without_prepared_stamp_is_adopted_without_changes(self):
        prepare(self.r.id,FrozenClock(self.r.prepares_at));self.r.refresh_from_db()
        m=Member.objects.filter(round=self.r).first();m.snapshot['city']='Ручная правка';m.save()
        ids=set(Member.objects.values_list('id',flat=True))
        self.r.prepared_at=None;self.r.state='closed';self.r.save()
        self.publish();self.r.refresh_from_db();m.refresh_from_db()
        self.assertIsNotNone(self.r.published_at);self.assertEqual(ids,set(Member.objects.values_list('id',flat=True)))
        self.assertEqual(m.snapshot['city'],'Ручная правка')
    def test_partial_draft_is_preserved_and_cancellation_is_sent_once(self):
        prepare(self.r.id,FrozenClock(self.r.prepares_at));Member.objects.filter(round=self.r).first().delete()
        remaining=Member.objects.filter(round=self.r).get();snapshot=remaining.snapshot.copy()
        result=self.publish();self.assertEqual(result.status,'cancelled')
        self.publish(self.start+timedelta(minutes=30))
        self.r.refresh_from_db();remaining.refresh_from_db()
        self.assertEqual(self.r.state,'cancelled');self.assertIsNone(self.r.published_at)
        self.assertEqual(remaining.snapshot,snapshot);self.assertEqual(self.r.enrollments.count(),2)
        self.assertEqual(Notification.objects.filter(kind='round_cancelled').count(),2)
        sent=[];drain(FrozenClock(self.start),lambda *args:sent.append(args) or 1,force=True,kinds=notification_kinds('publish'),round_id=self.r.id)
        drain(FrozenClock(self.start),lambda *args:self.fail('must not resend'),force=True,kinds=notification_kinds('publish'),round_id=self.r.id)
        self.assertEqual(len(sent),2)
        self.assertTrue(all('активность не состоится' in x[1] for x in sent))
    def test_temporary_database_failure_does_not_cancel_and_can_retry(self):
        with patch('myteam.matching.Meeting.objects.create',side_effect=DatabaseError('isolated')):
            self.assertTrue(self.publish().error)
        self.r.refresh_from_db();self.assertIsNone(self.r.cancelled_at)
        self.assertFalse(Member.objects.exists());self.assertFalse(self.publish().error)
        self.r.refresh_from_db();self.assertIsNotNone(self.r.published_at)
    def test_missing_all_publication_runs_finalizes_failure_after_cutoff(self):
        result=self.publish(self.start+timedelta(hours=6,minutes=5))
        self.assertEqual(result.status,'cancelled');self.r.refresh_from_db()
        self.assertEqual(self.r.cancellation_reason,'publication_missed')
        self.assertEqual(Notification.objects.filter(kind='round_cancelled').count(),2)
        context=dashboard_context(self.people[0],self.start+timedelta(hours=7))
        self.assertEqual(context['week'].state,'cancelled');self.assertTrue(context['registration_open'])
        self.assertEqual(context['next_round'].activity,'code_names')
    def test_unfinished_code_names_cancels_without_changing_announced_activity(self):
        game=ensure_round(self.r.ends_at)
        for p in self.people:Enrollment.objects.create(round=game,person=p)
        from copy import copy
        placeholder=copy(ACTIVITIES['code_names']);placeholder.signup_only=True
        with patch.dict(ACTIVITIES,{'code_names':placeholder}):
            self.assertEqual(execute('prepare',FrozenClock(game.prepares_at)).status,'blocked')
            result=execute('publish',FrozenClock(game.starts_at))
        game.refresh_from_db();self.assertEqual(result.status,'cancelled')
        self.assertEqual(game.activity,'code_names');self.assertEqual(game.enrollments.count(),2)
        self.assertEqual(Notification.objects.filter(kind='round_cancelled',round=game).count(),2)
        next_round=Round.objects.get(starts_at=game.ends_at)
        self.assertNotEqual(next_round.activity,'code_names')
        self.assertTrue(ready(next_round.activity,next_round.rules_version))
    def test_manual_pause_is_never_overridden_by_cutoff(self):
        self.r.publication_paused=True;self.r.selection={**self.r.selection,'pause_origin':'manual'};self.r.save()
        self.assertEqual(self.publish(self.start+timedelta(hours=7)).status,'paused')
        self.r.refresh_from_db();self.assertIsNone(self.r.cancelled_at);self.assertFalse(Notification.objects.filter(kind='round_cancelled').exists())
    def test_unknown_activity_cannot_break_calendar_or_silently_be_replaced(self):
        self.r.activity='deleted_format';self.r.selection={'title':'Объявленное название'};self.r.save()
        self.assertEqual(self.publish().status,'cancelled')
        self.r.refresh_from_db();self.assertEqual(self.r.activity_title,'Объявленное название')
        self.assertEqual(self.r.activity,'deleted_format')
    def test_late_manual_recovery_never_sends_old_week_messages(self):
        self.publish(self.r.ends_at+timedelta(days=10))
        self.assertFalse(Notification.objects.filter(kind='round_cancelled').exists())
    def test_card_creates_next_signup_even_if_every_action_was_missed(self):
        # No publication/action has run; first page load must still offer the next round.
        context=dashboard_context(self.people[0],self.start+timedelta(days=8))
        self.assertIsNotNone(context['next_round']);self.assertTrue(context['registration_open'])

    def test_system_placeholder_pause_releases_when_adapter_becomes_ready(self):
        game=ensure_round(self.r.ends_at)
        game.publication_paused=True;game.selection={**game.selection,'pause_origin':'placeholder'};game.save()
        for p in self.people:Enrollment.objects.create(round=game,person=p)
        class ReadyFixture(RandomCoffee):
            key='code_names'
            title='Code Names'
        with patch.dict(ACTIVITIES,{'code_names':ReadyFixture()}):
            self.assertFalse(execute('publish',FrozenClock(game.starts_at)).error)
        game.refresh_from_db()
        self.assertIsNotNone(game.published_at);self.assertFalse(game.publication_paused)
        self.assertEqual(game.enrollments.count(),2)
    def test_owner_can_convert_placeholder_pause_to_manual_pause(self):
        from django.core.management import call_command
        import io
        game=ensure_round(self.r.ends_at)
        call_command('pause_round',round_date='2026-11-04',stdout=io.StringIO())
        game.refresh_from_db();self.assertEqual(game.selection['pause_origin'],'manual')
        result=execute('publish',FrozenClock(game.starts_at))
        self.assertEqual(result.status,'paused');game.refresh_from_db();self.assertIsNone(game.cancelled_at)


from django.test import TransactionTestCase
from django.db import close_old_connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
class ConcurrentSelectionTests(TransactionTestCase):
    def test_simultaneous_creation_freezes_one_choice_and_one_round(self):
        barrier=Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                r=ensure_round(datetime(2027,3,3,9,tzinfo=MOSCOW))
                return r.id,r.activity,r.selection
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(Round.objects.count(),1)
