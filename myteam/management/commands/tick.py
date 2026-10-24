from django.core.management.base import BaseCommand
from myteam.clock import Clock
from myteam.jobs import tick
from myteam.notifications import drain
class Command(BaseCommand):
    help='Run due stages transactionally, then deliver a bounded outbox batch.'
    def add_arguments(self,parser):
        parser.add_argument('--delivery-limit',type=int,default=100)
    def handle(self,*args,**options):
        clock=Clock()
        tick(clock)
        self.stdout.write(f'Outbox processed: {drain(clock,limit=min(max(options['delivery_limit'],1),100))}')
