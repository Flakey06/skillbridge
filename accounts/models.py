import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings


def generate_referral_code():
    return uuid.uuid4().hex[:10].upper()


class UserProfile(models.Model):
    ROLE_CHOICES = [('candidate', 'Candidate'), ('recruiter', 'Recruiter')]
    PLAN_CHOICES = [('free', 'SkillBridge Free'), ('pro', 'SkillBridge Pro')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    plan_expires_at = models.DateTimeField(blank=True, null=True)
    pro_trial_started_at = models.DateTimeField(blank=True, null=True)
    trial_started_at = models.DateTimeField(blank=True, null=True)
    profile_data = models.JSONField(default=dict, blank=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    profile_photo = models.FileField(upload_to='profile_photos/', blank=True, null=True)
    referral_code = models.CharField(max_length=10, unique=True, default=generate_referral_code)

    @property
    def is_pro(self):
        return self.plan == 'pro' and (
            self.plan_expires_at is None or self.plan_expires_at > timezone.now()
        )

    @property
    def display_name(self):
        name = str((self.profile_data or {}).get("name", "")).strip()
        return name or self.user.get_full_name().strip() or self.user.username

    @property
    def initials(self):
        display_name = self.display_name
        parts = display_name.split()
        if len(parts) > 1:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        return display_name[:2].upper()

    def __str__(self):
        return f'{self.user.username} ({self.role})'


class Payment(models.Model):
    PROVIDER_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('paynow', 'PayNow / DBS'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('past_due', 'Past due'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='SGD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    external_id = models.CharField(max_length=255, blank=True)
    checkout_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} · {self.provider} · {self.status}'


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    kind = models.CharField(max_length=40, default="update")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient.username} · {self.title}"


class Referral(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("rewarded", "Rewarded"),
        ("partial", "Partially rewarded"),
        ("failed", "Failed"),
    ]
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referrals_made",
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_received",
    )
    referral_code = models.CharField(max_length=10)
    reward_days = models.PositiveSmallIntegerField(default=7)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    rewarded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.referrer} referred {self.referred_user}"
