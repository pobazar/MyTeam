from datetime import datetime
from unittest.mock import patch
from django.test import TestCase
from myteam.activities import ACTIVITIES,get_activity
from myteam.activities.coffee import RandomCoffee
from myteam.clock import FrozenClock,MOSCOW
from myteam.models import Person,Round,Enrollment,Member,Achievement
from myteam.rounds import ensure_round
from myteam.matching import prepare
from myteam.jobs import publish
from myteam.feedback import save_feedback
class ActivityContractTests(TestCase):
    def test_another_format_reuses_lifecycle_without_coffee_group_sizes_or_awards(self):
        class IsolatedFormat(RandomCoffee):
            key='isolated_format'
            title='Изолированный формат'
            minimum_participants=4
            achievement_key='isolated_achievement'
            def build_groups(self,people,history,rng=None):return [people] if len(people)>=4 else []
            def valid_distribution(self,count,sizes,unmatched):return sizes==[4] and unmatched==0
            def achievement_earned(self,person_id):return False
        with self.assertRaises(KeyError):get_activity('random_coffee',99)
        with patch.dict(ACTIVITIES,{'isolated_format':IsolatedFormat()}):
            r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW));r.activity='isolated_format';r.save()
            for i in range(4):
                p=Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m')
                Enrollment.objects.create(person=p,round=r)
            prepare(r.id,FrozenClock(r.prepares_at));publish(r.id,FrozenClock(r.starts_at))
            self.assertEqual(r.meetings.count(),1)
            self.assertEqual(Member.objects.count(),4)
            save_feedback(p.id,r.meetings.get().id,{'outcome':'yes','impression':'positive','again':'yes'},FrozenClock(r.starts_at))
            self.assertFalse(Achievement.objects.exists())
            self.assertEqual(r.activity_title,'Изолированный формат')
