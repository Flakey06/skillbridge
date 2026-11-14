"""Recruiter interviews, scheduling, and reschedule requests."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from accounts.calendar import build_month_calendar, calendar_download_or_reminder
from applications.forms import InterviewForm
from applications.interview_conflicts import scheduling_conflicts
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
    selected_application = None
    if request.method == "GET" and request.GET.get("application"):
        selected_application = get_object_or_404(applications, pk=request.GET["application"], status="shortlisted")
    interview_id = request.POST.get("interview_id")
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
            conflicts = scheduling_conflicts(
                interview.application,
                interview.created_by,
                interview.proposed_start,
                interview.proposed_end,
                exclude_interview=interview,
            )
            if conflicts:
                messages.error(request, "That proposed time now conflicts with another candidate or recruiter interview. Choose another time.")
            else:
                interview.scheduled_start = interview.proposed_start
                interview.scheduled_end = interview.proposed_end
                interview.reschedule_status = "accepted"
                interview.response_status = "accepted"
                interview.reschedule_message = "The recruiter accepted the proposed interview time."
                interview.save(update_fields=[
                    "scheduled_start",
                    "scheduled_end",
                    "reschedule_status",
                    "response_status",
                    "reschedule_message",
                ])
                notify(
                    interview.application.candidate,
                    "Interview reschedule accepted",
                    f"Your interview for {interview.application.job.title} was moved to {timezone.localtime(interview.scheduled_start):%d %b %Y, %H:%M}.",
                    "interview",
                )
                messages.success(request, "Reschedule accepted and the calendar was updated.")
        else:
            interview.reschedule_status = "rejected"
            interview.response_status = "awaiting"
            interview.reschedule_message = "The recruiter rejected the proposed interview time."
            interview.save(update_fields=["reschedule_status", "response_status", "reschedule_message"])
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
        if not interview_id:
            schedule_conflicts = scheduling_conflicts(
                application,
                request.user,
                form.cleaned_data["scheduled_start"],
                form.cleaned_data.get("scheduled_end"),
            )
        if schedule_conflicts and request.POST.get("confirm_conflict") != "yes":
            selected_application = application
            messages.warning(request, "This interview may clash with another approved interview. Review the overlap before continuing.")
        else:
            interview.save()
            if interview_id:
                interview.reschedule_status = "accepted"
                interview.response_status = "awaiting"
                interview.reschedule_message = "The recruiter changed the interview time."
                interview.save(update_fields=["reschedule_status", "response_status", "reschedule_message"])
                notify(
                    application.candidate,
                    "Interview time updated",
                    f"The recruiter changed your interview for {application.job.title} to {timezone.localtime(interview.scheduled_start):%d %b %Y, %H:%M}.",
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
                    f"An interview for {application.job.title} is scheduled for {timezone.localtime(interview.scheduled_start):%d %b %Y, %H:%M}.{contact_copy}",
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
        calendar=calendar_data,
        calendar_changed=calendar_changed,
        schedule_conflicts=schedule_conflicts,
    ))
