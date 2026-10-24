from django.core.management.base import BaseCommand
from myteam.clock import Clock
from myteam.monitoring import monitor
class Command(BaseCommand):
    def handle(self,*args,**options):
        failures=monitor(Clock())
        self.stdout.write('Operational checks: '+('degraded' if failures else 'ok'))
