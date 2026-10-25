from django.core.management.base import BaseCommand,CommandError
from myteam.clock import Clock
from myteam.scheduled_events import EVENTS,execute,notification_kinds,publication_report
from myteam.notifications import drain
class Command(BaseCommand):
    help='Run one explicit weekly event and deliver only its round-specific outbox.'
    def add_arguments(self,parser):
        parser.add_argument('--event',required=True,choices=EVENTS)
        parser.add_argument('--round-date',help='Wednesday YYYY-MM-DD; no clock override')
        parser.add_argument('--delivery-limit',type=int,default=100)
    def handle(self,*args,**options):
        clock=Clock();event=options['event']
        try:outcome=execute(event,clock,options.get('round_date'))
        except (ValueError,TypeError):raise CommandError('Invalid Wednesday round date.')
        if outcome.round is None:
            self.stdout.write('Skipped: outside allowed event window.');return
        processed=drain(clock,limit=min(max(options['delivery_limit'],1),100),kinds=notification_kinds(event),round_id=outcome.round.id)
        if event=='publish':publication_report(outcome.round.id,clock)
        self.stdout.write(f'Event: {event}; outbox processed: {processed}; status: {outcome.status}')
        if outcome.error:raise CommandError('Event failed; inspect persisted job state.')
