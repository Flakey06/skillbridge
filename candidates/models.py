from django.conf import settings
from django.db import models


class CandidateProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidate_profile",
    )
    career_area = models.CharField(max_length=100, blank=True)
    specialisation = models.CharField(max_length=100, blank=True)
    education_level = models.CharField(max_length=100, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    certifications = models.TextField(blank=True)
    linkedin_url = models.URLField(blank=True)
    work_experience = models.TextField(blank=True)
    portfolio_links = models.TextField(blank=True)
    awards = models.TextField(blank=True)
    technical_skills = models.TextField(blank=True)
    visa_status = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=40, blank=True)
    profile_complete_percent = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} candidate profile"


class Certification(models.Model):
    title = models.CharField(max_length=200)
    provider = models.CharField(max_length=150)
    career_area = models.CharField(max_length=100, blank=True)
    specialisation = models.CharField(max_length=100, blank=True)
    skills = models.TextField(blank=True)
    url = models.URLField(blank=True)
    cost = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    is_recognised = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider", "title"]

    def __str__(self):
        return f"{self.title} — {self.provider}"


class CandidateMilestone(models.Model):
    STATUS_CHOICES = [
        ("planned", "Planned"),
        ("in_progress", "In progress"),
        ("pending_verification", "Pending verification"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
    ]

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_milestones",
    )
    certification = models.ForeignKey(
        Certification,
        on_delete=models.CASCADE,
        related_name="candidate_milestones",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planned")
    certificate_id = models.CharField(max_length=150, blank=True)
    verification_url = models.URLField(blank=True, max_length=500)
    verification_method = models.CharField(max_length=50, blank=True)
    verification_details = models.TextField(blank=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviewed_certificates")
    review_comment = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    evidence_file = models.FileField(upload_to="certificate_evidence/", blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "certification"],
                name="unique_candidate_milestone",
            )
        ]
