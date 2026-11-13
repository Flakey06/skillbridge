from django.conf import settings
from django.db import models

from employers.choices import INDUSTRY_CHOICES
from employers.models import Company


class Job(models.Model):
    ROLE_CHOICES = [
        ("ai_engineer", "AI engineer"),
        ("software_engineer", "Software engineer"),
        ("backend_engineer", "Backend engineer"),
        ("frontend_engineer", "Frontend engineer"),
        ("data_scientist", "Data scientist"),
        ("data_analyst", "Data analyst"),
        ("data_engineer", "Data engineer"),
        ("ml_engineer", "Machine learning engineer"),
        ("ux_ui_designer", "UX / UI designer"),
        ("product_manager", "Product manager"),
        ("cybersecurity", "Cybersecurity specialist"),
        ("other", "Other"),
    ]
    EMPLOYMENT_TYPES = [
        ("internship", "Internship"),
        ("full_time", "Full-time"),
        ("part_time", "Part-time"),
        ("contract", "Contract"),
        ("temporary", "Temporary"),
    ]
    EXPERIENCE_LEVELS = [
        ("entry", "Entry level"),
        ("junior", "Junior"),
        ("mid", "Mid-level"),
        ("senior", "Senior"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("open", "Open"),
        ("closed", "Closed"),
    ]
    CURRENCY_CHOICES = [
        ("SGD", "SGD — Singapore dollar"),
        ("USD", "USD — US dollar"),
        ("EUR", "EUR — Euro"),
        ("GBP", "GBP — Pound sterling"),
        ("AUD", "AUD — Australian dollar"),
    ]
    SALARY_PERIOD_CHOICES = [
        ("hour", "per hour"),
        ("month", "per month"),
        ("year", "per year"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_jobs",
    )
    title = models.CharField(max_length=200)
    role_type = models.CharField(max_length=40, choices=ROLE_CHOICES, default="other")
    description = models.TextField()
    industry = models.CharField(max_length=100, choices=INDUSTRY_CHOICES, blank=True)
    location = models.CharField(max_length=120, blank=True)
    employment_type = models.CharField(max_length=30, choices=EMPLOYMENT_TYPES)
    experience_level = models.CharField(
        max_length=30,
        choices=EXPERIENCE_LEVELS,
        default="entry",
    )
    salary_min = models.PositiveIntegerField(blank=True, null=True)
    salary_max = models.PositiveIntegerField(blank=True, null=True)
    salary_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="SGD")
    salary_period = models.CharField(max_length=10, choices=SALARY_PERIOD_CHOICES, default="month")
    stipend = models.CharField(max_length=120, blank=True)
    required_skills = models.TextField(blank=True)
    preferred_skills = models.TextField(blank=True)
    skill_weights = models.JSONField(default=dict, blank=True)
    evidence_weights = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    skill_weights = models.JSONField(default=dict, blank=True)
    evidence_weights = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} at {self.company.name}"

    @staticmethod
    def split_skills(value):
        return [
            item.strip()
            for item in value.replace("\n", ",").split(",")
            if item.strip()
        ]

    @property
    def required_skill_list(self):
        return self.split_skills(self.required_skills)

    @property
    def preferred_skill_list(self):
        return self.split_skills(self.preferred_skills)

    @property
    def salary_display(self):
        if self.salary_min is None and self.salary_max is None:
            return self.stipend
        symbol = {"SGD": "S$", "USD": "US$", "EUR": "€", "GBP": "£", "AUD": "A$"}.get(self.salary_currency, self.salary_currency)
        if self.salary_min is not None and self.salary_max is not None:
            amount = f"{symbol}{self.salary_min:,}–{symbol}{self.salary_max:,}"
        elif self.salary_min is not None:
            amount = f"From {symbol}{self.salary_min:,}"
        else:
            amount = f"Up to {symbol}{self.salary_max:,}"
        period = dict(self.SALARY_PERIOD_CHOICES).get(self.salary_period, self.salary_period)
        return f"{amount} {period}"
