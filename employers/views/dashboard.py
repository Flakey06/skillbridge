"""Recruiter dashboard."""

from django.shortcuts import render
from django.utils import timezone
from accounts.decorators import recruiter_required
from applications.models import Interview, JobApplication
from jobs.models import Job
from .common import _context


@recruiter_required
def dashboard(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs)
    interviews = Interview.objects.filter(application__in=applications)
    now = timezone.now()
    return render(
        request,
        "employers/dashboard.html",
        _context(
            request,
            active_jobs=jobs.filter(status="open").count(),
            applicant_count=applications.count(),
            shortlisted_count=applications.filter(status="shortlisted").count(),
            interview_count=interviews.filter(scheduled_start__gte=now).count(),
            recent_applications=applications.select_related("candidate", "job")[:5],
            upcoming_interviews=interviews.filter(scheduled_start__gte=now).select_related("application__job")[:5],
            pending_reschedules=interviews.filter(reschedule_status="pending").select_related("application__candidate", "application__job"),
        ),
    )
