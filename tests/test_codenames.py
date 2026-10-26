from datetime import datetime,timedelta
from itertools import chain
import random
from unittest.mock import patch
from django.test import TestCase
from django.contrib.sessions.backends.db import SessionStore
from myteam.activities.codenames import CodeNames,group_sizes,GAME_URL
from myteam.clock import MOSCOW,FrozenClock
from myteam.models import Person,Enrollment,Member,Meeting,Notification,Achievement,Feedback
from myteam.rounds import ensure_round
from myteam.scheduled_events import execute
from myteam.feedback import save_feedback
from myteam.rotation import ready

class CodeNamesTests(TestCase):
    def people(self,count):
        return [Person.objects.create(telegram_id=100+i,chat_id=100+i,full_name=f'Участник {i}',team='Команда',city='Москва',city_key='moskva',username=f'qa_person_{i}',onboarding_done=True,delivery_verified_at=self.start) for i in range(count)]
    def setUp(self):self.start=datetime(2026,11,4,9,tzinfo=MOSCOW)
    def test_distribution_sizes_cover_every_attendee_and_prefer_four_then_five(self):
        a=CodeNames()
        expected={0:[],1:[],3:[],4:[4],5:[5],6:[6],7:[7],8:[4,4],9:[4,5],10:[5,5],11:[5,6],12:[4,4,4],13:[4,4,5],14:[4,5,5],15:[5,5,5],16:[4,4,4,4]}
        for count,sizes in expected.items():
            self.assertEqual(sorted(group_sizes(count)),sizes)
        for count in range(101):
            sizes=group_sizes(count)
            self.assertTrue(a.valid_distribution(count,sizes,count if count<4 else 0))
            if count>=4:self.assertEqual(sum(sizes),count);self.assertTrue(all(4<=n<=7 for n in sizes))
            if count not in (6,7,11):self.assertTrue(all(n<=5 for n in sizes))
        self.assertFalse(a.valid_distribution(8,[5],3));self.assertFalse(a.valid_distribution(8,[3,5],0))
    def test_matching_has_no_duplicates_and_avoids_repeating_an_entire_group(self):
        people=self.people(8);a=CodeNames()
        from itertools import combinations
        history={frozenset((x.id,y.id)):1 for group in (people[:4],people[4:]) for x,y in combinations(group,2)}
        groups=a.build_groups(people,history,random.Random(13))
        self.assertEqual(sorted(map(len,groups)),[4,4])
        self.assertEqual({p.id for p in people},{p.id for p in chain.from_iterable(groups)})
        self.assertEqual(sum(map(len,groups)),8)
        self.assertNotIn({p.id for p in people[:4]},[{p.id for p in g} for g in groups])
    def test_full_cycle_preserves_enrollment_draft_roles_and_awards_only_game_badge(self):
        r=ensure_round(self.start);people=self.people(11)
        r.publication_paused=True;r.selection={**r.selection,'pause_origin':'placeholder'};r.save()
        for p in people:Enrollment.objects.create(person=p,round=r)
        result=execute('prepare',FrozenClock(r.prepares_at));self.assertFalse(result.error)
        self.assertEqual(r.meetings.count(),2)
        ids=set(Member.objects.filter(round=r).values_list('id',flat=True))
        member=Member.objects.filter(round=r).first();member.snapshot['city']='Ручная правка';member.save()
        execute('prepare',FrozenClock(r.prepares_at))
        self.assertEqual(ids,set(Member.objects.filter(round=r).values_list('id',flat=True)))
        self.assertFalse(execute('publish',FrozenClock(r.starts_at)).error)
        r.refresh_from_db();self.assertIsNotNone(r.published_at);self.assertFalse(r.publication_paused)
        self.assertEqual(sorted(m.members.count() for m in r.meetings.all()),[5,6])
        self.assertEqual(Notification.objects.filter(round=r,kind='meeting').count(),11)
        for message in Notification.objects.filter(round=r,kind='meeting'):
            self.assertTrue(message.text.startswith('Code Names'));self.assertNotIn('Random Coffee',message.text)
            self.assertIn('рассуждайте вслух',message.text);self.assertIn('не подсказывайте',message.text)
            self.assertIn('https://t.me/qa_person_',message.text)
            self.assertEqual(message.payload['reply_markup']['inline_keyboard'][1][0]['url'],GAME_URL)
        for meeting in r.meetings.all():
            self.assertIn(meeting.activity_data['organizer_person_id'],[str(m.person_id) for m in meeting.members.all()])
        p=people[0];m=Member.objects.get(round=r,person=p)
        data={'outcome':'yes','rating':5,'comment':'Интересно было услышать разные ассоциации.'}
        save_feedback(p.id,m.meeting_id,data,FrozenClock(r.ends_at+timedelta(days=40)))
        save_feedback(p.id,m.meeting_id,data,FrozenClock(r.ends_at+timedelta(days=40)))
        self.assertEqual(Achievement.objects.filter(person=p,key='first_code_names').count(),1)
        self.assertFalse(Achievement.objects.filter(person=p,key='first_coffee').exists())
        self.assertEqual(Feedback.objects.get(member=m).revision,1)
        self.assertFalse(Enrollment.objects.exclude(round=r).exists())
    def test_too_few_people_are_unmatched_and_no_failed_game_badge_is_granted(self):
        r=ensure_round(self.start)
        for p in self.people(3):Enrollment.objects.create(person=p,round=r)
        execute('prepare',FrozenClock(r.prepares_at));execute('publish',FrozenClock(r.starts_at))
        self.assertEqual(r.unmatched_set.count(),3);self.assertFalse(r.meetings.exists())
        self.assertEqual(Notification.objects.filter(kind='unmatched').count(),3);self.assertFalse(Achievement.objects.exists())
    def test_profile_returns_both_badges_in_two_queries_and_game_link_is_scoped(self):
        r=ensure_round(self.start);people=self.people(4)
        for p in people:Enrollment.objects.create(person=p,round=r)
        execute('publish',FrozenClock(self.start))
        p=people[0]
        for key in ('first_coffee','first_code_names'):Achievement.objects.create(person=p,key=key)
        session=SessionStore();session['person_id']=str(p.id);session.create()
        headers={'HTTP_AUTHORIZATION':'Bearer '+session.session_key}
        self.client.get('/api/profile/',**headers)  # Establish CSRF once, as in the existing performance contract.
        self.client.cookies.clear()
        with self.assertNumQueries(2):response=self.client.get('/api/profile/',**headers)
        awards=response.json()['achievements'];self.assertEqual([a['key'] for a in awards],['first_coffee','first_code_names'])
        self.assertEqual(awards[1]['image'],'first-code-names.png');self.assertIsNotNone(awards[1]['earned_at'])
        with patch('myteam.clock.Clock.now',return_value=self.start):
            current=self.client.get('/api/activities/',**headers).json()['current']
        self.assertEqual(current['activity_title'],'Code Names');self.assertEqual(current['game_url'],GAME_URL)
        self.assertEqual(len(current['participants']),4);self.assertEqual(sum(m['is_organizer'] for m in current['participants']),1)
        self.assertTrue(ready('code_names',1))
        self.client.cookies.clear()
        self.assertEqual(self.client.get(f'/api/meetings/{Member.objects.get(round=r,person=p).meeting_id}/feedback/').status_code,401)
    def test_no_outcome_does_not_award_the_game_achievement(self):
        r=ensure_round(self.start);people=self.people(4)
        for p in people:Enrollment.objects.create(person=p,round=r)
        execute('publish',FrozenClock(self.start));m=Member.objects.get(person=people[0],round=r)
        save_feedback(people[0].id,m.meeting_id,{'outcome':'no'},FrozenClock(self.start))
        self.assertFalse(Achievement.objects.exists())
