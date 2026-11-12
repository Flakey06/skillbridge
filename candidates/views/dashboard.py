"""Candidate dashboard data."""

from django.utils import timezone
from accounts.dashboard_helpers import dashboard_greeting
from django.db.models import Exists, OuterRef
from applications.models import Interview, JobApplication, SavedJob
from jobs.models import Job
from ..career_paths import career_progress
from .common import _current_profile, _selected_career_interests, _completion_percent


def dashboard_context(request):
    applications = JobApplication.objects.filter(candidate=request.user)
    interviews = Interview.objects.filter(application__candidate=request.user).exclude(application__status="withdrawn").select_related("application__job__company")
    now = timezone.now()
    profile = _current_profile(request)
    profile_data = (profile.profile_data if profile else {}) or {}
    interests = _selected_career_interests(profile_data)
    return {
        "role": "candidate",
        "greeting": dashboard_greeting(),
        "has_pro": profile.is_pro if profile else False,
        "application_count": applications.count(),
        "interview_count": interviews.filter(scheduled_start__gte=now).count(),
        "saved_count": SavedJob.objects.filter(candidate=request.user).count(),
        "profile_completion": _completion_percent(profile) if profile else 0,
        "upcoming_interviews": interviews.filter(scheduled_start__gte=now)[:1],
        "recent_jobs": Job.objects.filter(status="open").select_related("company").annotate(
            is_saved=Exists(SavedJob.objects.filter(candidate=request.user, job_id=OuterRef("pk"))),
            has_applied=Exists(JobApplication.objects.filter(candidate=request.user, job_id=OuterRef("pk"))),
        )[:3],
        "career_progress": career_progress(request.user, interests),
    }
