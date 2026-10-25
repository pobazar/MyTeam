from datetime import datetime
from unittest.mock import patch
from django.test import TestCase
from myteam.clock import MOSCOW,FrozenClock
from myteam.activity_plan import ensure_planned_rounds
from myteam.rounds import ensure_round,enroll,RuleError
from myteam.models import Person,Enrollment,Round,Notification
from myteam.matching import prepare
from myteam.invitations import schedule_invites,invitation_window
from myteam.read_models import dashboard_context

class ActivityPlanTests(TestCase):
    def setUp(self):
        self.now=datetime(2026,10,26,10,tzinfo=MOSCOW)
        self.p=Person.objects.create(telegram_id=1,chat_id=1,full_name='Анна',team='Дизайн',city='Москва',city_key='moskva',onboarding_done=True,delivery_verified_at=self.now)
    def test_coffee_then_code_names_visible_and_enrollable_from_wednesday(self):
        coffee=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        ensure_planned_rounds(self.now);ensure_planned_rounds(self.now)
        game=Round.objects.get(starts_at=datetime(2026,11,4,9,tzinfo=MOSCOW))
        self.assertEqual(coffee.activity,'random_coffee');self.assertEqual(game.activity_title,'Code Names')
        self.assertTrue(game.publication_paused)
        context=dashboard_context(self.p,coffee.starts_at)
        self.assertEqual(context['next_round'].id,game.id);self.assertTrue(context['registration_open'])
        enroll(self.p.id,game.id,True,FrozenClock(coffee.starts_at))
        self.assertTrue(Enrollment.objects.get(person=self.p,round=game).active)
        # A repeat deploy preserves both the round and its registration.
        ensure_planned_rounds(coffee.starts_at)
        self.assertEqual(Enrollment.objects.count(),1)
        other=Person.objects.create(telegram_id=2,chat_id=2,full_name='Борис',team='ИТ',city='Москва',city_key='moskva',onboarding_done=True,delivery_verified_at=self.now)
        schedule_invites(game,FrozenClock(invitation_window(game)[0]))
        invite=Notification.objects.get(kind='signup_invite')
        self.assertEqual(invite.person_id,other.id);self.assertTrue(invite.text.startswith('Code Names'))
        with self.assertRaisesMessage(RuleError,'Пока доступна только запись'):prepare(game.id,FrozenClock(game.prepares_at))
        self.assertFalse(game.meetings.exists())
    def test_existing_open_round_keeps_id_and_enrollment_when_changing_title(self):
        game=ensure_round(datetime(2026,11,4,9,tzinfo=MOSCOW));game.activity='random_coffee';game.publication_paused=False;game.save()
        e=Enrollment.objects.create(person=self.p,round=game)
        ensure_planned_rounds(self.now)
        e.refresh_from_db();game.refresh_from_db()
        self.assertEqual(game.activity,'code_names');self.assertEqual(e.round_id,game.id);self.assertTrue(e.active)
    def test_prepared_round_cannot_be_rewritten(self):
        game=ensure_round(datetime(2026,11,4,9,tzinfo=MOSCOW));game.activity='random_coffee';game.prepared_at=self.now;game.state='prepared';game.save()
        with self.assertRaises(RuleError):ensure_planned_rounds(self.now)
        game.refresh_from_db();self.assertEqual(game.activity,'random_coffee')
