from django.core.management.base import BaseCommand
from myteam.clock import Clock
from myteam.notifications import drain
class Command(BaseCommand):
    help = 'Deliver a bounded outbox batch; disabled unless SEND_TELEGRAM=true.'
    def handle(self,*args,**options):
        self.stdout.write(f'Processed: {drain(Clock())}')
