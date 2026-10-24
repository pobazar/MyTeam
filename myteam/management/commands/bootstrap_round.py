from django.core.management.base import BaseCommand
from myteam.clock import Clock
from myteam.rounds import upcoming_start,ensure_round
class Command(BaseCommand):
    def handle(self,*args,**options):
        r=ensure_round(upcoming_start(Clock().now()))
        self.stdout.write(f'Round: {r.starts_at.isoformat()}')
