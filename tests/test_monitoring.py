from datetime import timedelta
from django.test import TestCase,override_settings
from django.utils import timezone
from myteam.clock import FrozenClock
from myteam.models import Person,Incident,Notification,RuntimeLock
from myteam.monitoring import monitor
class MonitoringTests(TestCase):
    @override_settings(OWNER_TELEGRAM_ID='42',OWNER_CHAT_ID='42')
    def test_missing_cron_is_independent_deduplicated_and_recovers(self):
        clock=FrozenClock(timezone.now())
        Person.objects.create(telegram_id=42,chat_id=42,delivery_verified_at=clock.now())
        for _ in range(3):self.assertIn('scheduler_stale',monitor(clock))
        self.assertEqual(Incident.objects.count(),1)
        self.assertEqual(Notification.objects.filter(kind='incident').count(),1)
        RuntimeLock.objects.create(key='scheduler',heartbeat=clock.now())
        self.assertEqual(monitor(clock),[])
        monitor(clock)
        self.assertEqual(Notification.objects.filter(kind='recovery').count(),1)
    def test_isolated_blocked_bot_is_not_mass_incident(self):
        clock=FrozenClock(timezone.now())
        RuntimeLock.objects.create(key='scheduler',heartbeat=clock.now())
        Notification.objects.create(key='blocked',kind='test',chat_id=1,text='',status='failed',last_error='telegram_403')
        self.assertEqual(monitor(clock),[])
