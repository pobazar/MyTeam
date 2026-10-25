from django.core.management.base import BaseCommand
from myteam.clock import Clock
from myteam.rounds import upcoming_start,ensure_round
class Command(BaseCommand):
    def handle(self,*args,**options):
        from myteam.activity_plan import ensure_planned_rounds
        now=Clock().now()
        ensure_planned_rounds(now)
        from myteam.rounds import ensure_calendar
        ensure_calendar(now)
        r=ensure_round(upcoming_start(now))
        self.stdout.write(f'Round: {r.starts_at.isoformat()}')
