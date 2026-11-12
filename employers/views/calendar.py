"""Recruiter interviews, scheduling, and reschedule requests."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from accounts.calendar import build_month_calendar, calendar_download_or_reminder
from applications.forms import InterviewForm
from applications.models import Interview, JobApplication
from jobs.models import Job
from .common import _context


@recruiter_required
def calendar(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(
        job__in=jobs,
        status__in=["shortlisted", "interview"],
    ).select_related("candidate", "job")
    interviews = Interview.objects.filter(application__in=applications).select_related("application__candidate", "application__job")
    download, calendar_changed = calendar_download_or_reminder(request, interviews)
    if download is not None:
        return download
    interview_id = request.POST.get("interview_id")
    interview = None
    if interview_id:
        interview = get_object_or_404(interviews, pk=interview_id)
    action = request.POST.get("action")
    if request.method == "POST" and interview and action in {"accept_reschedule", "reject_reschedule"}:
        if interview.reschedule_status != "pending":
            messages.error(request, "That reschedule request is no longer pending.")
        elif action == "accept_reschedule" and interview.proposed_start:
            interview.scheduled_start = interview.proposed_start
            interview.scheduled_end = interview.proposed_end
            interview.reschedule_status = "accepted"
            interview.reschedule_message = "The recruiter accepted the proposed interview time."
            interview.save(update_fields=[
                "scheduled_start",
                "scheduled_end",
                "reschedule_status",
                "reschedule_message",
            ])
            notify(
                interview.application.candidate,
                "Interview reschedule accepted",
                f"Your interview for {interview.application.job.title} was moved to {interview.scheduled_start:%d %b %Y, %H:%M}.",
                "interview",
            )
            messages.success(request, "Reschedule accepted and the calendar was updated.")
        else:
            interview.reschedule_status = "rejected"
            interview.reschedule_message = "The recruiter rejected the proposed interview time."
            interview.save(update_fields=["reschedule_status", "reschedule_message"])
            notify(
                interview.application.candidate,
                "Interview reschedule declined",
                f"Your requested time change for {interview.application.job.title} was declined by the recruiter.",
                "interview",
            )
            messages.success(request, "Reschedule request rejected.")
        return redirect("recruiter_calendar")
    form = InterviewForm(request.POST or None, instance=interview)
    if request.method == "POST" and form.is_valid():
        interview = form.save(commit=False)
        if interview.pk is None:
            application = get_object_or_404(applications, pk=request.POST.get("application_id"))
            interview.application = application
            interview.created_by = request.user
        else:
            application = interview.application
        interview.save()
        if interview_id:
            interview.reschedule_status = "accepted"
            interview.reschedule_message = "The recruiter changed the interview time."
            interview.save(update_fields=["reschedule_status", "reschedule_message"])
            notify(
                application.candidate,
                "Interview time updated",
                f"The recruiter changed your interview for {application.job.title} to {interview.scheduled_start:%d %b %Y, %H:%M}.",
                "interview",
            )
        application.status = "interview"
        application.save(update_fields=["status", "updated_at"])
        if not interview_id:
            notify(
                application.candidate,
                "Interview scheduled",
                f"An interview for {application.job.title} is scheduled for {interview.scheduled_start:%d %b %Y, %H:%M}.",
                "interview",
            )
        messages.success(request, "Interview rescheduled." if interview_id else "Interview scheduled.")
        return redirect("recruiter_calendar")
    now = timezone.now()
    calendar_data = build_month_calendar(interviews, request.GET.get("month"), request.GET.get("date"))
    return render(request, "employers/calendar.html", _context(
        request,
        interviews=interviews,
        upcoming_interviews=interviews.filter(scheduled_start__gte=now),
        past_interviews=interviews.filter(scheduled_start__lt=now),
        pending_reschedules=interviews.filter(reschedule_status="pending"),
        applications=applications,
        form=form,
        calendar=calendar_data,
        calendar_changed=calendar_changed,
    ))
