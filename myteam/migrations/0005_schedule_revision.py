from django.db import migrations
from django.utils import timezone

def update_future_schedule(apps,schema_editor):
    Round=apps.get_model('myteam','Round')
    # Preserve historical and manually prepared/published rounds and every profile/history row.
    for r in Round.objects.filter(prepared_at__isnull=True,published_at__isnull=True,starts_at__gt=timezone.now()):
        r.prepares_at=r.closes_at
        r.save(update_fields=['prepares_at'])
    Notification=apps.get_model('myteam','Notification')
    Notification.objects.filter(kind='feedback_last',status='pending').update(status='cancelled')

class Migration(migrations.Migration):
    dependencies=[('myteam','0004_alter_loginattempt_confirmation_code_and_more')]
    operations=[migrations.RunPython(update_future_schedule,migrations.RunPython.noop)]
