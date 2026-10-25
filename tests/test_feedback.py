from datetime import timedelta
from django.test import TestCase
from tests import test_privacy
from myteam.clock import FrozenClock
from myteam.jobs import publish
from myteam.feedback import save_feedback,schedule_requests,request_times,FeedbackForm
from myteam.models import Achievement,Feedback,Notification
from myteam.notifications import drain
from myteam.rounds import RuleError
class FeedbackTests(TestCase):
    def setUp(self):
        test_privacy.PrivacyTests.setUp(self);publish(self.r.id,FrozenClock(self.r.starts_at));self.r.refresh_from_db()
    def test_reminder_boundaries_and_suppression_at_send(self):
        first,last=request_times(self.r)
        self.assertEqual((first.weekday(),first.hour),(1,9))
        self.assertEqual(last,self.r.ends_at)
        schedule_requests(self.r,FrozenClock(first-timedelta(microseconds=1)))
        self.assertEqual(Notification.objects.filter(kind='feedback_first').count(),0)
        schedule_requests(self.r,FrozenClock(first))
        self.assertEqual(Notification.objects.filter(kind='feedback_first').count(),2)
        save_feedback(self.people[0].id,self.meeting.id,{'outcome':'no','comment':'Не удалось найти общее время.'},FrozenClock(first))
        calls=[]
        Notification.objects.filter(kind='meeting').delete()
        drain(FrozenClock(first),lambda *a:calls.append(a) or 1,force=True)
        self.assertEqual(len(calls),1)
        schedule_requests(self.r,FrozenClock(first+timedelta(hours=12)));self.assertEqual(Notification.objects.filter(kind='feedback_last').count(),0)
        self.assertEqual(Notification.objects.filter(kind='feedback_first').count(),2)
        schedule_requests(self.r,FrozenClock(self.r.ends_at));self.assertEqual(Notification.objects.filter(kind='feedback_last').count(),0)
    def test_achievement_change_and_deadline(self):
        now=FrozenClock(self.r.starts_at)
        data={'outcome':'yes','rating':5,'comment':''}
        for _ in range(2):save_feedback(self.people[0].id,self.meeting.id,data,now)
        self.assertEqual(Achievement.objects.count(),1)
        self.assertEqual(Feedback.objects.get().revision,1)
        save_feedback(self.people[0].id,self.meeting.id,{'outcome':'no','comment':'Не удалось найти общее время.'},now)
        self.assertEqual(Achievement.objects.count(),0)
        self.assertTrue(Feedback.objects.get().final)
        with self.assertRaises(RuleError):save_feedback(self.people[0].id,self.meeting.id,{'outcome':'no','comment':'Не удалось найти общее время.'},FrozenClock(self.r.ends_at+timedelta(days=7)))
    def test_yes_requires_all_fields(self):
        self.assertFalse(FeedbackForm({'outcome':'yes'}).is_valid())

    def test_no_reason_is_optional_and_rating_is_cleared(self):
        form=FeedbackForm({'outcome':'no','rating':5,'comment':''})
        self.assertTrue(form.is_valid());self.assertIsNone(form.cleaned_data['rating'])
        answer=save_feedback(self.people[0].id,self.meeting.id,{'outcome':'no'},FrozenClock(self.r.starts_at))
        self.assertTrue(answer.final);self.assertEqual(answer.comment,'');self.assertIsNone(answer.rating)
        self.assertFalse(Achievement.objects.filter(person=self.people[0]).exists())
