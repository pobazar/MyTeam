from datetime import timedelta
from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone
from myteam.models import Person, Round, Enrollment
class SchemaTests(TestCase):
    def test_enrollment_identity_is_stable_and_unique(self):
        p = Person.objects.create(telegram_id=42)
        now = timezone.now()
        r = Round.objects.create(starts_at=now, ends_at=now+timedelta(days=7), closes_at=now, prepares_at=now)
        Enrollment.objects.create(person=p, round=r)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(person=p, round=r)
        p.username = 'newname'
        p.save()
        self.assertEqual(Enrollment.objects.get().person_id, p.id)
