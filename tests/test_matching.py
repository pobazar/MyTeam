from datetime import datetime
from django.test import TestCase
from myteam.clock import FrozenClock,MOSCOW
from myteam.models import Person,Enrollment,Member,Unmatched,TeamGroup
from myteam.rounds import ensure_round,RuleError
from myteam.matching import prepare,validate_draft,select_groups
class MatchingTests(TestCase):
    def test_sizes_and_restart_preserve_manual_snapshot(self):
        for count in (0,1,2,3,4,5,8,9):
            r=ensure_round(datetime(2027,1,6+count,9,tzinfo=MOSCOW))
            for i in range(count):
                p=Person.objects.create(telegram_id=count*100+i,first_name='А',last_name='Б',team='Т',city='Город',city_key='gorod')
                Enrollment.objects.create(person=p,round=r)
            clock=FrozenClock(r.prepares_at)
            prepare(r.id,clock)
            self.assertTrue(validate_draft(r))
            self.assertEqual(Member.objects.filter(round=r).count(),count if count!=1 else 0)
            self.assertEqual(Unmatched.objects.filter(round=r).count(),int(count==1))
            ids=set(Member.objects.filter(round=r).values_list('id',flat=True))
            if ids:
                m=Member.objects.filter(round=r).first();m.snapshot['city']='Правка';m.save()
                prepare(r.id,clock)
                m.refresh_from_db();self.assertEqual(m.snapshot['city'],'Правка')
            self.assertEqual(ids,set(Member.objects.filter(round=r).values_list('id',flat=True)))
    def test_invalid_draft_is_rejected(self):
        r=ensure_round(datetime(2026,10,28,9,tzinfo=MOSCOW))
        for i in range(2):
            p=Person.objects.create(telegram_id=i+1,first_name='А',last_name='Б',team='Т',city='М',city_key='m')
            Enrollment.objects.create(person=p,round=r)
        prepare(r.id,FrozenClock(r.prepares_at))
        Member.objects.filter(round=r).first().delete()
        with self.assertRaises(RuleError):validate_draft(r)
    def test_repeats_take_priority_over_teams(self):
        team=TeamGroup.objects.create(canonical='same')
        p=[Person.objects.create(telegram_id=i,team_group=team if i<2 else None) for i in range(4)]
        history={frozenset((p[0].id,p[2].id)):100,frozenset((p[0].id,p[3].id)):200}
        groups=select_groups(p,history)
        self.assertTrue(any(set(x.id for x in g)=={p[0].id,p[1].id} for g in groups))
