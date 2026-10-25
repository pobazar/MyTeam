from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from myteam.clock import Clock
from myteam.models import Round
from myteam.scheduled_events import target_start
from myteam.rotation import lock_rotation

class Command(BaseCommand):
    help='Explicit owner publication pause; automatic recovery never overrides this pause.'
    def add_arguments(self,parser):
        parser.add_argument('--round-date',required=True)
        parser.add_argument('--resume',action='store_true')
    def handle(self,*args,**options):
        try:start=target_start('publish',Clock().now(),options['round_date'])
        except (ValueError,TypeError):raise CommandError('Expected Wednesday YYYY-MM-DD.')
        with transaction.atomic():
            lock_rotation()
            try:r=Round.objects.select_for_update().get(starts_at=start)
            except Round.DoesNotExist:raise CommandError('Round does not exist.')
            if r.published_at or r.state in ('cancelled','expired'):raise CommandError('Round already finalized.')
            r.publication_paused=not options['resume']
            r.selection={**r.selection,'pause_origin':'manual' if r.publication_paused else 'released'}
            r.save(update_fields=['publication_paused','selection'])
        self.stdout.write('Publication paused.' if r.publication_paused else 'Publication resumed.')
