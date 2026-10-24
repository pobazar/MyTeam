from datetime import timedelta
from django.db import connection
from django.conf import settings
from .models import Round,RuntimeLock,Notification
from .jobs import record_incident,resolve_incident

def inspect(clock):
    now=clock.now()
    failures=[]
    heartbeat=RuntimeLock.objects.filter(key='scheduler').values_list('heartbeat',flat=True).first()
    if not heartbeat or now-heartbeat>timedelta(minutes=10):failures.append('scheduler_stale')
    if Round.objects.filter(prepares_at__lt=now-timedelta(minutes=10),ends_at__gt=now,prepared_at__isnull=True).exists():failures.append('preparation_late')
    if Round.objects.filter(starts_at__lt=now-timedelta(minutes=10),ends_at__gt=now,published_at__isnull=True,publication_paused=False).exists():failures.append('publication_late')
    recent=Notification.objects.filter(created_at__gte=now-timedelta(hours=1))
    failed=recent.filter(status__in=['failed','unknown']).exclude(last_error='telegram_403').count()
    if failed>=3 and failed/max(recent.count(),1)>=.5:failures.append('delivery_mass_failure')
    backlog=Notification.objects.filter(status='pending',next_attempt_at__lt=now-timedelta(minutes=15)).exists()
    if backlog:failures.append('delivery_backlog')
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:
            cursor.execute('select pg_database_size(current_database())')
            size=cursor.fetchone()[0]
        limit=int(getattr(settings,'DB_WARNING_BYTES',0))
        if limit and size>=limit:failures.append('database_size_warning')
    return failures

def monitor(clock):
    failures=inspect(clock)
    all_keys=('scheduler_stale','preparation_late','publication_late','delivery_mass_failure','delivery_backlog','database_size_warning')
    for key in all_keys:
        if key in failures:record_incident('monitor:'+key,'Требуется проверка: '+key,clock)
        else:resolve_incident('monitor:'+key,clock)
    return failures
