from django.conf import settings
from django.db import models

from .choices import INDUSTRY_CHOICES


class Company(models.Model):
    name = models.CharField(max_length=200)
    website = models.URLField(blank=True)
    industry = models.CharField(max_length=100, choices=INDUSTRY_CHOICES, blank=True)
    description = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    linkedin_organization_id = models.CharField(max_length=100, blank=True)
    verification_status = models.CharField(max_length=30, default="pending")
    verification_comment = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviewed_companies")
    reviewed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name


class RecruiterProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recruiter_profile",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="recruiters",
        blank=True,
        null=True,
    )
    job_title = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.user.username} recruiter profile"
