"""Recruiter interviews, scheduling, and reschedule requests."""

from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from accounts.calendar import build_month_calendar, calendar_download_or_reminder
from applications.forms import InterviewForm
from applications.models import Interview, JobApplication
from jobs.models import Job
from .common import _context, _recruiter


def _scheduling_conflicts(application, recruiter, start, end, exclude_interview=None):
    """Return candidate/recruiter interviews overlapping a proposed slot."""
    proposed_end = end or start + timedelta(hours=1)
    candidate_interviews = Interview.objects.filter(
        application__candidate=application.candidate,
    ).select_related("application__job", "created_by")
    recruiter_interviews = Interview.objects.filter(
        created_by=recruiter,
    ).select_related("application__candidate", "application__job")
    if exclude_interview:
        candidate_interviews = candidate_interviews.exclude(pk=exclude_interview.pk)
        recruiter_interviews = recruiter_interviews.exclude(pk=exclude_interview.pk)
    conflicts = []
    seen = set()
    for kind, existing in [
        *(("Candidate", item) for item in candidate_interviews),
        *(("Recruiter", item) for item in recruiter_interviews),
    ]:
        existing_end = existing.scheduled_end or existing.scheduled_start + timedelta(hours=1)
        if existing.scheduled_start < proposed_end and existing_end > start and existing.pk not in seen:
            seen.add(existing.pk)
            conflicts.append({
                "kind": kind,
                "title": existing.application.job.title,
                "candidate": existing.application.candidate.username,
                "start": timezone.localtime(existing.scheduled_start),
                "end": timezone.localtime(existing_end),
            })
    return conflicts


@recruiter_required
def calendar(request):
    recruiter = _recruiter(request)
    jobs = Job.objects.filter(company=recruiter.company) if recruiter.company_id else Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(
        job__in=jobs,
        status__in=["shortlisted", "interview"],
    ).select_related("candidate", "job")
    interviews = Interview.objects.filter(application__in=applications).select_related("application__candidate", "application__job")
    download, calendar_changed = calendar_download_or_reminder(request, interviews)
    if download is not None:
        return download
    selected_application = None
    if request.method == "GET" and request.GET.get("application"):
        selected_application = get_object_or_404(applications, pk=request.GET["application"], status="shortlisted")
    interview_id = request.POST.get("interview_id") or request.GET.get("edit")
    interview = None
    if interview_id:
        interview = get_object_or_404(interviews, pk=interview_id)
    action = request.POST.get("action")
    if request.method == "POST" and interview and action == "record_outcome":
        attendance_status = request.POST.get("attendance_status")
        if attendance_status not in dict(Interview.ATTENDANCE_CHOICES):
            messages.error(request, "Choose a valid attendance outcome.")
        else:
            interview.attendance_status = attendance_status
            interview.recruiter_feedback = request.POST.get("recruiter_feedback", "").strip()
            interview.serious_concern = request.POST.get("serious_concern") == "yes"
            interview.save(update_fields=["attendance_status", "recruiter_feedback", "serious_concern"])
            if attendance_status == "no_show":
                notify(
                    interview.application.candidate,
                    "Interview marked as no-show",
                    f"The interview for {interview.application.job.title} was recorded as a no-show. Contact the recruiter or request a new time if needed.",
                    "interview",
                )
            messages.success(request, "Interview outcome recorded. You can reschedule a no-show using the Reschedule button.")
        return redirect("recruiter_calendar")
    if request.method == "POST" and interview and action in {"accept_reschedule", "reject_reschedule"}:
        if interview.reschedule_status != "pending":
            messages.error(request, "That reschedule request is no longer pending.")
        elif action == "accept_reschedule" and interview.proposed_start:
            conflicts = _scheduling_conflicts(
                interview.application,
                request.user,
                interview.proposed_start,
                interview.proposed_end,
                exclude_interview=interview,
            )
            if conflicts:
                messages.error(request, "That proposed time is no longer available. Ask the candidate to choose another time.")
                return redirect("recruiter_calendar")
            interview.scheduled_start = interview.proposed_start
            interview.scheduled_end = interview.proposed_end
            interview.reschedule_status = "accepted"
            interview.candidate_response = "accepted"
            interview.reschedule_message = "The recruiter accepted the proposed interview time."
            interview.save(update_fields=[
                "scheduled_start",
                "scheduled_end",
                "reschedule_status",
                "reschedule_message",
                "candidate_response",
            ])
            notify(
                interview.application.candidate,
                "Interview reschedule accepted",
                f"Your interview for {interview.application.job.title} was moved to {timezone.localtime(interview.scheduled_start):%d %b %Y, %H:%M} SGT.",
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
    schedule_conflicts = []
    if request.method == "POST" and form.is_valid():
        interview = form.save(commit=False)
        if interview.pk is None:
            application = get_object_or_404(applications, pk=request.POST.get("application_id"), status="shortlisted")
            interview.application = application
            interview.created_by = request.user
        else:
            application = interview.application
        schedule_conflicts = _scheduling_conflicts(
            application,
            request.user,
            form.cleaned_data["scheduled_start"],
            form.cleaned_data.get("scheduled_end"),
            exclude_interview=interview if interview.pk else None,
        )
        if schedule_conflicts:
            selected_application = application
            messages.error(request, "This time is unavailable because it overlaps another interview. Choose a different time.")
        else:
            if interview_id:
                interview.candidate_response = "pending"
            interview.save()
            if interview_id:
                interview.reschedule_status = "accepted"
                interview.reschedule_message = "The recruiter changed the interview time."
                interview.save(update_fields=["reschedule_status", "reschedule_message", "candidate_response"])
                notify(
                    application.candidate,
                    "Interview time updated",
                    f"The recruiter changed your interview for {application.job.title} to {timezone.localtime(interview.scheduled_start):%d %b %Y, %H:%M} SGT.",
                    "interview",
                )
            application.status = "interview"
            application.save(update_fields=["status", "updated_at"])
            if not interview_id:
                contact_label = interview.get_contact_method_display()
                contact_copy = f" Contact method: {contact_label}"
                if interview.contact_details:
                    contact_copy += f" ({interview.contact_details})"
                notify(
                    application.candidate,
                    "Interview scheduled",
                    f"An interview for {application.job.title} is scheduled for {timezone.localtime(interview.scheduled_start):%d %b %Y, %H:%M} SGT.{contact_copy}",
                    "interview",
                )
            messages.success(request, "Interview rescheduled." if interview_id else "Interview scheduled and added to the candidate's SkillBridge calendar.")
            return redirect("recruiter_calendar")
    now = timezone.now()
    calendar_data = build_month_calendar(interviews, request.GET.get("month"), request.GET.get("date"))
    return render(request, "employers/calendar.html", _context(
        request,
        interviews=interviews,
        upcoming_interviews=interviews.filter(scheduled_start__gte=now),
        past_interviews=interviews.filter(scheduled_start__lt=now),
        pending_reschedules=interviews.filter(reschedule_status="pending"),
        applications=applications.filter(status="shortlisted"),
        selected_application=selected_application,
        form=form,
        editing_interview=interview,
        editor_open=bool(interview_id or request.GET.get("create") or request.GET.get("application") or request.method == "POST"),
        calendar=calendar_data,
        calendar_changed=calendar_changed,
        schedule_conflicts=schedule_conflicts,
    ))
