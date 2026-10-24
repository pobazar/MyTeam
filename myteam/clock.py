from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from django.utils import timezone
MOSCOW = ZoneInfo('Europe/Moscow')
class Clock:
    def now(self):
        return timezone.now()
@dataclass
class FrozenClock(Clock):
    instant: datetime
    def now(self):
        if self.instant.tzinfo is None:
            raise ValueError('Clock requires a timezone-aware instant')
        return self.instant
