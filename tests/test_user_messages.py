from unittest.mock import patch
from django.test import TestCase
from myteam.activities import ACTIVITIES
from myteam.activities.coffee import RandomCoffee
from myteam.clock import FrozenClock
from myteam.jobs import publish
from myteam.feedback import schedule_requests,request_times
from myteam.invitations import schedule_invites,invitation_window
from myteam.models import Notification,Member,Unmatched
from myteam.rounds import ensure_round
from myteam.user_messages import unmatched
from tests import test_privacy

class UserMessageTests(TestCase):
    def setUp(self):
        test_privacy.PrivacyTests.setUp(self)
    def test_other_activity_name_links_and_no_dates_in_all_four_templates(self):
        class AnotherActivity(RandomCoffee):
            key='isolated_other'
            title='Прогулка & общение'
            def instructions(self,same_city):return 'Погуляйте вместе.'
            def organizer_instructions(self):return 'Выберите маршрут. '
        with patch.dict(ACTIVITIES,{'isolated_other':AnotherActivity()}):
            self.r.refresh_from_db();self.r.activity='isolated_other';self.r.save()
            member=Member.objects.get(person=self.people[0],meeting=self.meeting)
            member.snapshot.update(full_name='<Анна>',username='anna_example');member.save()
            publish(self.r.id,FrozenClock(self.r.starts_at));self.r.refresh_from_db()
            schedule_requests(self.r,FrozenClock(request_times(self.r)[0]))
            upcoming=ensure_round(self.r.ends_at);upcoming.activity='isolated_other';upcoming.save()
            schedule_invites(upcoming,FrozenClock(invitation_window(upcoming)[0]))
            text,payload=unmatched(self.r)
            self.assertIn('не собралось достаточно участников для активности',text)
            self.assertEqual(payload['reply_markup']['inline_keyboard'][0][0]['text'],'Открыть МАЙТИМ')
            texts=[text]+list(Notification.objects.filter(kind__in=('meeting','feedback_first','signup_invite')).values_list('text',flat=True))
            self.assertEqual(len(texts),8)  # 2 assignments, 2 feedbacks, 3 invitations, unmatched.
            for text in texts:
                self.assertTrue(text.startswith('Прогулка &amp; общение'))
                for forbidden in ('Random Coffee','МАЙТИМ ·','28.10','04.11','Участие добровольное'):
                    self.assertNotIn(forbidden,text)
            assignment=Notification.objects.filter(kind='meeting').first()
            self.assertIn('<a href="https://t.me/anna_example">&lt;Анна&gt;</a>',assignment.text)
            self.assertIn('tg://user?id=2',assignment.text)
            self.assertIn('организатор',assignment.text)
            request=Notification.objects.filter(kind='feedback_first').first()
            self.assertIn('Как прошла активность?',request.text)
            self.assertEqual(request.payload['reply_markup']['inline_keyboard'][0][0]['text'],'Оставить оценку')
            invite=Notification.objects.filter(kind='signup_invite').first()
            buttons=invite.payload['reply_markup']['inline_keyboard'][0]
            self.assertEqual([b['text'] for b in buttons],['Записаться','Отказаться'])
            self.assertTrue(all(len(b['callback_data'].encode())<=64 for b in buttons))
