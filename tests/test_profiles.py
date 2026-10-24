from django.test import TestCase
from myteam.profiles import team_identity, normalize_city
class ProfileTests(TestCase):
    def test_transliteration_and_abbreviation_are_conservative(self):
        a,_=team_identity('Команда Роста')
        b,_=team_identity('Komanda-Rosta')
        self.assertEqual(a,b)
        full,_=team_identity('Customer Success Team')
        self.assertEqual(full,team_identity('CST')[0])
        self.assertNotEqual(full,team_identity('Customer Support Team')[0])
        self.assertEqual(team_identity('CST')[1],'uncertain')
    def test_cities(self):
        self.assertEqual(normalize_city('Москва'),normalize_city('Moscow'))
