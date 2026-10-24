from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from myteam.clock import FrozenClock
from myteam.models import Notification
from myteam.notifications import enqueue,drain
from myteam.telegram import DeliveryError
class QueueTests(TestCase):
    def setUp(self):self.clock=FrozenClock(timezone.now())
    def test_deduplication_and_confirmed_success(self):
        for _ in range(2):enqueue('same','test',42,'hello',now=self.clock.now())
        calls=[]
        drain(self.clock,lambda *args: calls.append(args) or 1,force=True)
        drain(self.clock,lambda *args: calls.append(args) or 2,force=True)
        self.assertEqual(len(calls),1)
        self.assertEqual(Notification.objects.get().status,'sent')
    def test_errors_do_not_block_others_and_rate_limit_is_preserved(self):
        for i in range(3):enqueue(str(i),'test',i,'hello',now=self.clock.now())
        def transport(chat,text):
            if chat==0:raise DeliveryError('telegram_403',permanent=True)
            if chat==1:raise DeliveryError('telegram_429',retry_after=120)
            return 42
        drain(self.clock,transport,force=True)
        self.assertEqual(Notification.objects.get(key='0').status,'failed')
        n=Notification.objects.get(key='1')
        self.assertEqual(n.status,'pending')
        self.assertEqual(n.next_attempt_at,self.clock.now()+timedelta(seconds=120))
        self.assertEqual(Notification.objects.get(key='2').status,'sent')
    def test_unknown_is_not_blindly_retried(self):
        enqueue('x','test',1,'hello',now=self.clock.now())
        def fail(*args):raise DeliveryError('transport_unknown',uncertain=True)
        drain(self.clock,fail,force=True)
        self.assertEqual(Notification.objects.get().status,'unknown')
        self.assertEqual(drain(self.clock,lambda *args:1,force=True),0)
