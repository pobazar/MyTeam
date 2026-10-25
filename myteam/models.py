import uuid
from django.db import models
from django.db.models import Q
from django.utils import timezone

class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        abstract = True

class TeamGroup(Entity):
    canonical = models.CharField(max_length=200, unique=True)

class Person(Entity):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=250, blank=True, default='', db_default='')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    team = models.CharField(max_length=200, blank=True)
    team_group = models.ForeignKey(TeamGroup, null=True, blank=True, on_delete=models.SET_NULL)
    team_confidence = models.CharField(max_length=20, default='unknown')
    city = models.CharField(max_length=150, blank=True)
    city_key = models.CharField(max_length=150, blank=True)
    chat_id = models.BigIntegerField(null=True)
    delivery_verified_at = models.DateTimeField(null=True)
    delivery_blocked = models.BooleanField(default=False)
    onboarding_done = models.BooleanField(default=False)
    @property
    def display_name(self):
        return self.full_name.strip() or f'{self.first_name} {self.last_name}'.strip()
    @property
    def complete(self):
        return all(v.strip() for v in (self.display_name, self.team, self.city_key))
    @property
    def reachable(self):
        return self.chat_id is not None and self.delivery_verified_at is not None and not self.delivery_blocked
    def __str__(self):
        return self.display_name

class LoginAttempt(Entity):
    confirmation_code = models.CharField(max_length=6, default='', db_default='', blank=True)
    confirmed_at = models.DateTimeField(null=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    person = models.ForeignKey(Person, null=True, on_delete=models.CASCADE)
    consumed_at = models.DateTimeField(null=True)

class Round(Entity):
    starts_at = models.DateTimeField(unique=True)
    ends_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    prepares_at = models.DateTimeField()
    activity = models.CharField(max_length=40, default='random_coffee')
    rules_version = models.PositiveSmallIntegerField(default=1)
    state = models.CharField(max_length=20, default='open', choices=[(s,s) for s in ('open','closed','prepared','published','completed','expired')])
    publication_paused = models.BooleanField(default=False)
    prepared_at = models.DateTimeField(null=True)
    published_at = models.DateTimeField(null=True)
    preparation_error = models.CharField(max_length=200, blank=True)
    @property
    def activity_title(self):
        from .activities import get_activity
        return get_activity(self.activity,self.rules_version).title
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F('starts_at')), name='round_positive_period')]

class Enrollment(Entity):
    person = models.ForeignKey(Person, on_delete=models.PROTECT)
    round = models.ForeignKey(Round, on_delete=models.PROTECT, related_name='enrollments')
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['person','round'],name='one_enrollment_per_round')]

class Meeting(Entity):
    round = models.ForeignKey(Round, on_delete=models.PROTECT, related_name='meetings')
    activity_data = models.JSONField(default=dict)

class Member(Entity):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='members')
    round = models.ForeignKey(Round, on_delete=models.PROTECT)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='memberships')
    snapshot = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['person','round'],name='one_meeting_per_round')]

class Unmatched(Entity):
    round = models.ForeignKey(Round, on_delete=models.PROTECT)
    person = models.ForeignKey(Person, on_delete=models.PROTECT)
    reason = models.CharField(max_length=40, default='insufficient_participants')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['person','round'],name='one_unmatched_per_round')]

class Feedback(Entity):
    member = models.OneToOneField(Member, on_delete=models.PROTECT, related_name='feedback')
    outcome = models.CharField(max_length=10, choices=[('yes','Да'),('pending','Пока нет'),('no','Не получилось')])
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    impression = models.CharField(max_length=15, blank=True)
    again = models.CharField(max_length=15, blank=True)
    comment = models.TextField(blank=True, max_length=3000)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5), name='feedback_rating_1_to_5')]
    @property
    def stars(self):
        return '★' * self.rating + '☆' * (5-self.rating) if self.rating else ''
    @property
    def final(self):
        from .activities import get_activity
        return get_activity(self.member.round.activity,self.member.round.rules_version).final_feedback(self)

class Achievement(Entity):
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='achievements')
    key = models.CharField(max_length=40)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['person','key'],name='one_achievement')]

class Job(Entity):
    key = models.CharField(max_length=150, unique=True)
    round = models.ForeignKey(Round, null=True, on_delete=models.PROTECT)
    completed_at = models.DateTimeField(null=True)
    error = models.CharField(max_length=200, blank=True)

class RuntimeLock(models.Model):
    key = models.CharField(primary_key=True, max_length=50)
    heartbeat = models.DateTimeField(null=True)

class Notification(Entity):
    payload = models.JSONField(default=dict, db_default={})
    key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=40)
    person = models.ForeignKey(Person, null=True, on_delete=models.PROTECT)
    chat_id = models.BigIntegerField()
    round = models.ForeignKey(Round, null=True, on_delete=models.PROTECT)
    text = models.TextField()
    status = models.CharField(max_length=20, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    leased_until = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField(null=True)
    telegram_message_id = models.BigIntegerField(null=True)
    class Meta:
        indexes = [models.Index(fields=['status','next_attempt_at'])]

class Incident(Entity):
    key = models.CharField(max_length=150, unique=True)
    summary = models.CharField(max_length=300)
    opened_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True)
    last_alert_at = models.DateTimeField(null=True)
    occurrences = models.PositiveIntegerField(default=1)

class TelegramUpdate(models.Model):
    update_id = models.BigIntegerField(primary_key=True)
    processed_at = models.DateTimeField(default=timezone.now)

class AnalyticsEvent(Entity):
    key = models.CharField(max_length=220, unique=True)
    kind = models.CharField(max_length=50)
    person = models.ForeignKey(Person, null=True, on_delete=models.PROTECT)
    round = models.ForeignKey(Round, null=True, on_delete=models.PROTECT)
    payload = models.JSONField(default=dict)
    class Meta:
        indexes = [models.Index(fields=['kind','created_at'])]
