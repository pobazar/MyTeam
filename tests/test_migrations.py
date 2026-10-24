from datetime import datetime,timedelta,timezone
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from unittest.mock import patch
class MigrationTests(TransactionTestCase):
    def test_existing_profiles_history_feedback_and_achievements_survive(self):
        executor=MigrationExecutor(connection)
        executor.migrate([('myteam','0001_initial')])
        old=executor.loader.project_state([('myteam','0001_initial')]).apps
        now=datetime(2026,10,28,6,tzinfo=timezone.utc)
        p=old.get_model('myteam','Person').objects.create(telegram_id=42,first_name='Имя',last_name='Фамилия',team='Команда',city='Москва',city_key='moskva')
        r=old.get_model('myteam','Round').objects.create(starts_at=now,ends_at=now+timedelta(days=7),closes_at=now-timedelta(hours=12),prepares_at=now-timedelta(hours=11),state='published',published_at=now)
        meeting=old.get_model('myteam','Meeting').objects.create(round=r)
        m=old.get_model('myteam','Member').objects.create(person=p,round=r,meeting=meeting,snapshot={'team':'Первоначальная'})
        f=old.get_model('myteam','Feedback').objects.create(member=m,outcome='yes',impression='positive',again='yes',comment='Сохранить')
        achievement=old.get_model('myteam','Achievement').objects.create(person=p,key='first_coffee')
        upcoming=old.get_model('myteam','Round').objects.create(starts_at=now+timedelta(days=7),ends_at=now+timedelta(days=14),closes_at=now+timedelta(days=7,hours=-12),prepares_at=now+timedelta(days=7,hours=-11))
        executor=MigrationExecutor(connection)
        with patch('django.utils.timezone.now',return_value=now-timedelta(days=1)):
            executor.migrate([('myteam','0005_schedule_revision')])
        new=executor.loader.project_state([('myteam','0005_schedule_revision')]).apps
        migrated=new.get_model('myteam','Round').objects.get(pk=upcoming.id)
        self.assertEqual(migrated.prepares_at,migrated.closes_at)
        self.assertEqual(new.get_model('myteam','Round').objects.get(pk=r.id).prepares_at,r.prepares_at)
        self.assertEqual(new.get_model('myteam','Person').objects.get(pk=p.id).telegram_id,42)
        self.assertEqual(new.get_model('myteam','Member').objects.get(pk=m.id).snapshot['team'],'Первоначальная')
        self.assertEqual(new.get_model('myteam','Feedback').objects.get(pk=f.id).comment,'Сохранить')
        self.assertTrue(new.get_model('myteam','Achievement').objects.filter(pk=achievement.id).exists())
        MigrationExecutor(connection).migrate([('myteam','0005_schedule_revision')])
        self.assertEqual(new.get_model('myteam','Person').objects.count(),1)
        # Old writers can still INSERT while additive migrations deploy.
        import uuid
        with connection.cursor() as cursor:
            cursor.execute("insert into myteam_notification (id,created_at,key,kind,chat_id,text,status,attempts,next_attempt_at,last_error) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",[uuid.uuid4(),now,'legacy-compatible','test',42,'isolated','pending',0,now,''])
            cursor.execute("insert into myteam_loginattempt (id,created_at,token_hash,expires_at) values (%s,%s,%s,%s)",[uuid.uuid4(),now,'legacy-compatible',now+timedelta(minutes=10)])

