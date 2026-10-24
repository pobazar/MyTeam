from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest import skipUnless
from django.db import connection,connections,close_old_connections
from django.test import TransactionTestCase
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Person,Enrollment,Member,Notification
from myteam.rounds import ensure_round,enroll
from myteam.jobs import tick
from myteam.notifications import enqueue,drain

@skipUnless(connection.vendor=='postgresql','Row-lock semantics require PostgreSQL')
class ConcurrencyTests(TransactionTestCase):
    def parallel(self,fn):
        def run(_):
            close_old_connections()
            try:return fn()
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:return list(executor.map(run,range(2)))
    def setUp(self):
        self.r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        self.p=Person.objects.create(telegram_id=1,first_name='А',last_name='Б',team='Т',city='М',city_key='m',chat_id=1,delivery_verified_at=self.r.closes_at)
    def test_parallel_enrollment_and_scheduler(self):
        clock=FrozenClock(self.r.closes_at.replace(hour=17))
        self.parallel(lambda:enroll(self.p.id,self.r.id,True,clock))
        self.assertEqual(Enrollment.objects.count(),1)
        p=Person.objects.create(telegram_id=2,first_name='А',last_name='Б',team='Т',city='М',city_key='m',chat_id=2,delivery_verified_at=self.r.closes_at)
        enroll(p.id,self.r.id,True,clock)
        self.parallel(lambda:tick(FrozenClock(self.r.prepares_at)))
        self.parallel(lambda:tick(FrozenClock(self.r.starts_at)))
        self.assertEqual(Member.objects.count(),2)
        self.assertEqual(Notification.objects.filter(kind='meeting').count(),2)
    def test_parallel_workers_send_each_message_once(self):
        clock=FrozenClock(self.r.closes_at)
        for i in range(8):enqueue(str(i),'test',i,'isolated',now=clock.now())
        calls=[]
        self.parallel(lambda:drain(clock,lambda chat,text:calls.append(chat) or chat,force=True))
        self.assertEqual(len(calls),8)
        self.assertEqual(len(set(calls)),8)
