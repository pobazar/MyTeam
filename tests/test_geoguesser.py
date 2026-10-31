from datetime import datetime
from itertools import chain
import random
from unittest.mock import patch
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from myteam.activities import get_activity
from myteam.activities.geoguesser import GeoGuesser,group_sizes,GAME_URL
from myteam.clock import MOSCOW,FrozenClock
from myteam.feedback import save_feedback
from myteam.models import Person,TeamGroup,Round,Enrollment,Member,Notification,Achievement
from myteam.rotation import ready
from myteam.scheduled_events import execute


class GeoGuesserTests(TestCase):
    def people(self,count):
        return [Person.objects.create(telegram_id=500+i,chat_id=500+i,full_name=f'Участник {i}',
            team='Команда',city='Москва',city_key='moskva',username=f'qa_geo_{i}',
            onboarding_done=True,delivery_verified_at=self.start) for i in range(count)]

    def setUp(self):
        self.start=datetime(2026,11,11,9,tzinfo=MOSCOW)
        self.activity=GeoGuesser()

    def round(self):
        from datetime import timedelta
        return Round.objects.create(starts_at=self.start,ends_at=self.start+timedelta(days=7),
            closes_at=self.start-timedelta(hours=12),prepares_at=self.start-timedelta(hours=12),
            activity='geoguesser',rules_version=1)

    def test_sizes_and_matching_cover_everyone_even_when_preferences_conflict(self):
        self.assertTrue(ready('geoguesser',1))
        self.assertIsInstance(get_activity('geoguesser',1),GeoGuesser)
        for count in range(101):
            sizes=group_sizes(count)
            self.assertTrue(self.activity.valid_distribution(count,sizes,count if count<3 else 0))
            if count>=3:
                self.assertEqual(sum(sizes),count)
                self.assertTrue(all(3<=s<=4 or (count==5 and s==5) for s in sizes))
        self.assertFalse(self.activity.valid_distribution(8,[3,5],0))
        people=self.people(11)
        team=TeamGroup.objects.create(canonical='same')
        for p in people:p.team_group_id=team.id
        from itertools import combinations
        history={frozenset((a.id,b.id)):1 for a,b in combinations(people,2)}
        for count in range(12):
            groups=self.activity.build_groups(people[:count],history,random.Random(13))
            flattened=list(chain.from_iterable(groups))
            self.assertEqual(len(flattened),count if count>=3 else 0)
            self.assertEqual({p.id for p in flattened},{p.id for p in people[:count]} if count>=3 else set())

    def test_matching_prefers_new_contacts_then_different_teams(self):
        people=self.people(6)
        teams=[TeamGroup.objects.create(canonical=str(i)) for i in range(3)]
        for i,p in enumerate(people):p.team_group_id=teams[i%3].id
        # Deterministically offer a repeated-contact candidate, a same-team
        # candidate, then a candidate with new contacts and three teams each.
        candidates=[people, [people[i] for i in (0,3,2,1,4,5)], [people[i] for i in (0,4,5,3,1,2)]]
        class Candidates:
            index=0
            def shuffle(self,items):
                items[:]=candidates[min(self.index,2)];self.index+=1
        history={frozenset((people[0].id,people[1].id)):1}
        groups=self.activity.build_groups(people,history,Candidates())
        self.assertEqual([{p.id for p in g} for g in groups],[{p.id for p in g} for g in (candidates[2][:3],candidates[2][3:])])

    def test_publication_roles_notifications_and_achievement_in_profile(self):
        r=self.round();people=self.people(5)
        for p in people:Enrollment.objects.create(person=p,round=r)
        for _ in range(2):
            result=execute('publish',FrozenClock(self.start))
            self.assertFalse(result.error);self.assertEqual(result.status,'ok')
        self.assertEqual(r.meetings.count(),1)
        self.assertEqual(Member.objects.filter(round=r).count(),5)
        meeting=r.meetings.get()
        organizer=meeting.activity_data['organizer_person_id']
        self.assertIn(organizer,[str(p.id) for p in people])
        messages=Notification.objects.filter(round=r,kind='meeting')
        self.assertEqual(messages.count(),5)
        for n in messages:
            self.assertIn('GeoGuesser',n.text)
            self.assertIn('выбирайте ответ сообща',n.text)
            self.assertEqual(n.payload['reply_markup']['inline_keyboard'][1][0]['url'],GAME_URL)
            self.assertEqual('Ты организуешь эту встречу' in n.text,str(n.person_id)==organizer)
        p=people[0]
        session=SessionStore();session['person_id']=str(p.id);session.create()
        headers={'HTTP_AUTHORIZATION':'Bearer '+session.session_key}
        with patch('myteam.clock.Clock.now',return_value=self.start):
            current=self.client.get('/api/activities/',**headers).json()['current']
        self.assertEqual(current['game_url'],GAME_URL)
        self.assertEqual(sum(p['is_organizer'] for p in current['participants']),1)
        data={'outcome':'yes','rating':4}
        for _ in range(2):save_feedback(p.id,meeting.id,data,FrozenClock(self.start))
        self.assertEqual(list(Achievement.objects.filter(person=p).values_list('key',flat=True)),['first_geoguesser'])
        save_feedback(people[1].id,meeting.id,{'outcome':'no'},FrozenClock(self.start))
        self.assertFalse(Achievement.objects.filter(person=people[1]).exists())
        award=self.client.get('/api/profile/',**headers).json()['achievements'][0]
        self.assertEqual(award['title'],'Мир в деталях')
        self.assertEqual(award['image'],'first-geoguesser.png')
        self.assertIsNotNone(award['earned_at'])

    def test_too_few_participants_receive_unmatched_result(self):
        r=self.round()
        for p in self.people(2):Enrollment.objects.create(person=p,round=r)
        result=execute('publish',FrozenClock(self.start))
        self.assertFalse(result.error)
        self.assertEqual(r.unmatched_set.count(),2)
        self.assertFalse(r.meetings.exists())
        self.assertEqual(Notification.objects.filter(round=r,kind='unmatched').count(),2)
        self.assertFalse(Achievement.objects.exists())
