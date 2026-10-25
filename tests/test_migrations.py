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
            executor.migrate([('myteam','0007_round_selection_and_cancellation')])
        new=executor.loader.project_state([('myteam','0007_round_selection_and_cancellation')]).apps
        migrated=new.get_model('myteam','Round').objects.get(pk=upcoming.id)
        self.assertEqual(migrated.prepares_at,migrated.closes_at)
        self.assertEqual(new.get_model('myteam','Round').objects.get(pk=r.id).prepares_at,r.prepares_at)
        self.assertEqual(new.get_model('myteam','Person').objects.get(pk=p.id).telegram_id,42)
        self.assertEqual(new.get_model('myteam','Member').objects.get(pk=m.id).snapshot['team'],'Первоначальная')
        self.assertEqual(new.get_model('myteam','Feedback').objects.get(pk=f.id).comment,'Сохранить')
        self.assertTrue(new.get_model('myteam','Achievement').objects.filter(pk=achievement.id).exists())
        self.assertIsNone(new.get_model('myteam','Feedback').objects.get(pk=f.id).rating)
        self.assertEqual(new.get_model('myteam','Feedback').objects.get(pk=f.id).impression,'positive')
        self.assertEqual(new.get_model('myteam','Person').objects.get(pk=p.id).full_name,'')
        from myteam.models import Person,Feedback
        self.assertEqual(Person.objects.get(pk=p.id).display_name,'Имя Фамилия')
        self.assertTrue(Feedback.objects.get(pk=f.id).final)
        MigrationExecutor(connection).migrate([('myteam','0007_round_selection_and_cancellation')])
        self.assertEqual(new.get_model('myteam','Person').objects.count(),1)
        previous=MigrationExecutor(connection).loader.project_state([('myteam','0006_profile_name_and_activity_rating')]).apps
        legacy_round=previous.get_model('myteam','Round').objects.create(starts_at=now+timedelta(days=21),ends_at=now+timedelta(days=28),closes_at=now+timedelta(days=21,hours=-12),prepares_at=now+timedelta(days=21,hours=-12))
        from myteam.models import Round
        self.assertEqual(Round.objects.get(pk=legacy_round.id).selection,{})
        self.assertEqual(Round.objects.get(pk=legacy_round.id).cancellation_reason,'')
        # The original ORM writer omits full_name; the DB default preserves compatibility.
        legacy=old.get_model('myteam','Person').objects.create(telegram_id=43,first_name='Другой',last_name='Участник')
        self.assertEqual(Person.objects.get(pk=legacy.id).full_name,'')
        self.assertEqual(Person.objects.get(pk=legacy.id).display_name,'Другой Участник')
        # Old writers can still INSERT while additive migrations deploy.
        import uuid
        with connection.cursor() as cursor:
            cursor.execute("insert into myteam_notification (id,created_at,key,kind,chat_id,text,status,attempts,next_attempt_at,last_error) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",[uuid.uuid4(),now,'legacy-compatible','test',42,'isolated','pending',0,now,''])
            cursor.execute("insert into myteam_loginattempt (id,created_at,token_hash,expires_at) values (%s,%s,%s,%s)",[uuid.uuid4(),now,'legacy-compatible',now+timedelta(minutes=10)])

