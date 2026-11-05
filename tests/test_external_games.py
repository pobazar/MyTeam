from datetime import datetime,timedelta
from itertools import chain,combinations
from types import SimpleNamespace
import random
from unittest.mock import patch
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from myteam.activities import get_activity
from myteam.activities.four_person import group_sizes
from myteam.achievements import CATALOG
from myteam.clock import FrozenClock,MOSCOW
from myteam.feedback import save_feedback
from myteam.models import Round,Person,Enrollment,Member,Notification,Achievement
from myteam.rotation import ready,choose
from myteam.scheduled_events import execute


class ExternalGamesTests(TestCase):
    keys=('gartic_phone','spyfall')

    def round_and_people(self,key,count):
        index=self.keys.index(key)
        start=datetime(2027,1,6+14*index,9,tzinfo=MOSCOW)
        r=Round.objects.create(starts_at=start,ends_at=start+timedelta(days=7),closes_at=start-timedelta(hours=12),
            prepares_at=start-timedelta(hours=12),activity=key,rules_version=1)
        people=[Person.objects.create(telegram_id=10000+index*100+i,chat_id=10000+index*100+i,
            full_name=f'Участник {i}',team='Команда',city='Москва',city_key='moskva',username=f'qa_game_{i}',
            onboarding_done=True,delivery_verified_at=start) for i in range(count)]
        for p in people:Enrollment.objects.create(round=r,person=p)
        return r,people

    def test_four_person_sizes_and_soft_preferences_cover_all_attendees(self):
        self.assertEqual(group_sizes(7),[7]);self.assertEqual(sorted(group_sizes(11)),[5,6])
        people=[SimpleNamespace(id=i,team_group_id=1) for i in range(100)]
        history={frozenset((a.id,b.id)):1 for a,b in combinations(people,2)}
        for key in self.keys:
            a=get_activity(key,1)
            self.assertTrue(ready(key,1))
            for count in range(101):
                with self.subTest(key=key,count=count):
                    groups=a.build_groups(people[:count],history,random.Random(13))
                    sizes=list(map(len,groups));flat=list(chain.from_iterable(groups))
                    self.assertTrue(a.valid_distribution(count,sizes,count if count<4 else 0))
                    self.assertEqual(len(flat),count if count>=4 else 0)
                    self.assertEqual(len({p.id for p in flat}),len(flat))
                    self.assertTrue(all(4<=size<=7 for size in sizes))
                    if count not in (6,7,11):self.assertTrue(all(size<=5 for size in sizes))
            self.assertFalse(a.valid_distribution(8,[3,5],0))

    def test_matching_prefers_new_contacts_and_different_teams(self):
        people=[SimpleNamespace(id=i,team_group_id=i%4) for i in range(8)]
        candidates=[people,[people[i] for i in (0,4,2,3,1,5,6,7)],[people[i] for i in (0,5,6,7,4,1,2,3)]]
        class Candidates:
            def __init__(self):self.index=0
            def shuffle(self,items):items[:]=candidates[min(self.index,2)];self.index+=1
        history={frozenset((0,1)):1}
        for key in self.keys:
            groups=get_activity(key,1).build_groups(people,history,Candidates())
            self.assertEqual([{p.id for p in g} for g in groups],[{p.id for p in candidates[2][:4]},{p.id for p in candidates[2][4:]}])

    def test_lifecycle_roles_messages_api_and_independent_achievements(self):
        for key in self.keys:
            with self.subTest(key=key):
                a=get_activity(key,1);r,people=self.round_and_people(key,11)
                self.assertEqual(execute('prepare',FrozenClock(r.prepares_at),r.starts_at.date().isoformat()).status,'ok')
                original={m.id:m.snapshot for m in Member.objects.filter(round=r)}
                for _ in range(2):self.assertEqual(execute('publish',FrozenClock(r.starts_at),r.starts_at.date().isoformat()).status,'ok')
                self.assertEqual(original,{m.id:m.snapshot for m in Member.objects.filter(round=r)})
                self.assertEqual(sorted(m.members.count() for m in r.meetings.all()),[5,6])
                messages=Notification.objects.filter(round=r,kind='meeting')
                self.assertEqual(messages.count(),11)
                for meeting in r.meetings.all():
                    organizer=meeting.activity_data['organizer_person_id']
                    self.assertIn(organizer,[str(m.person_id) for m in meeting.members.all()])
                    for member in meeting.members.all():
                        n=messages.get(person_id=member.person_id)
                        self.assertTrue(n.text.startswith(a.title))
                        self.assertEqual(n.payload['reply_markup']['inline_keyboard'][1][0]['url'],a.game_url)
                        self.assertEqual('Ты организуешь эту встречу' in n.text,str(member.person_id)==organizer)
                p=people[0];m=Member.objects.get(round=r,person=p)
                session=SessionStore();session['person_id']=str(p.id);session.create()
                headers={'HTTP_AUTHORIZATION':'Bearer '+session.session_key}
                self.client.cookies.clear()
                with patch('myteam.clock.Clock.now',return_value=r.starts_at):
                    current=self.client.get('/api/activities/',**headers).json()['current']
                self.assertEqual(current['activity_title'],a.title);self.assertEqual(current['game_url'],a.game_url)
                self.assertEqual(sum(p['is_organizer'] for p in current['participants']),1)
                for _ in range(2):save_feedback(p.id,m.meeting_id,{'outcome':'yes','rating':5},FrozenClock(r.starts_at))
                self.assertEqual(list(Achievement.objects.filter(person=p).values_list('key',flat=True)),[a.achievement_key])
                awards=self.client.get('/api/profile/',**headers).json()['achievements']
                self.assertEqual(awards[0]['title'],CATALOG[a.achievement_key]['title'])
                self.assertEqual(awards[0]['image'],CATALOG[a.achievement_key]['image'])
                self.assertIsNotNone(awards[0]['earned_at'])
                other=Member.objects.get(round=r,person=people[1])
                save_feedback(other.person_id,other.meeting_id,{'outcome':'no'},FrozenClock(r.starts_at))
                self.assertFalse(Achievement.objects.filter(person_id=other.person_id).exists())

    def test_insufficient_attendance_and_rotation_catalog(self):
        for key in self.keys:
            r,people=self.round_and_people(key,3)
            self.assertEqual(execute('publish',FrozenClock(r.starts_at),r.starts_at.date().isoformat()).status,'ok')
            self.assertFalse(r.meetings.exists());self.assertEqual(r.unmatched_set.count(),3)
            self.assertEqual(Notification.objects.filter(round=r,kind='unmatched').count(),3)
        _,selection=choose(datetime(2027,3,3,9,tzinfo=MOSCOW),random.Random(1))
        self.assertTrue(set(self.keys)<=set(selection['weights']))
        self.assertFalse(Achievement.objects.exists())

    def test_assignments_fit_telegram_limit_with_maximum_profiles(self):
        from html.parser import HTMLParser
        class VisibleText(HTMLParser):
            def __init__(self):super().__init__();self.parts=[]
            def handle_data(self,data):self.parts.append(data)
        for key in self.keys:
            r,people=self.round_and_people(key,7)
            for p in people:p.full_name='😀'*250;p.team='😀'*200;p.save()
            execute('publish',FrozenClock(r.starts_at),r.starts_at.date().isoformat())
            for n in Notification.objects.filter(round=r,kind='meeting'):
                parser=VisibleText();parser.feed(n.text)
                self.assertLessEqual(len(''.join(parser.parts).encode('utf-16-le'))//2,4096)
