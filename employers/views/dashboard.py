"""Recruiter dashboard."""

from matching.ml_model import predict_suitability
from django.shortcuts import render
from django.utils import timezone
from accounts.dashboard_helpers import dashboard_greeting
from accounts.decorators import recruiter_required
from applications.models import Interview, JobApplication
from jobs.models import Job
from .common import _context


@recruiter_required
def dashboard(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs)
    interviews = Interview.objects.filter(application__in=applications)
    has_pro = getattr(request.user, "profile", None)
    has_pro = has_pro.is_pro if has_pro else False
    recent_applications = applications.select_related("candidate", "job")[:5]
    if has_pro:
        for application in recent_applications:
            ml_prediction = predict_suitability(application.candidate, application.job)
            application.ml_prediction = ml_prediction
    now = timezone.now()
    return render(
        request,
        "employers/dashboard.html",
        _context(
            request,
            greeting=dashboard_greeting(),
            active_jobs=jobs.filter(status="open").count(),
            applicant_count=applications.count(),
            shortlisted_count=applications.filter(status="shortlisted").count(),
            interview_count=interviews.filter(scheduled_start__gte=now).count(),
            recent_applications=recent_applications,
            has_pro=has_pro,
            upcoming_interviews=interviews.filter(scheduled_start__gte=now).select_related("application__job")[:5],
            pending_reschedules=interviews.filter(reschedule_status="pending").select_related("application__candidate", "application__job"),
        ),
    )
