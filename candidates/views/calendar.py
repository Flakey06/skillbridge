"""Candidate interview calendar, notes, and reschedule requests."""

from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from accounts.notification_helpers import notify
from accounts.calendar import build_month_calendar, calendar_download_or_reminder
from accounts.decorators import candidate_required
from applications.forms import CandidateInterviewForm
from applications.models import Interview
from .common import _context


@candidate_required
def calendar(request):
    interviews = Interview.objects.filter(application__candidate=request.user).exclude(application__status="withdrawn").select_related("application__job__company")
    download, calendar_changed = calendar_download_or_reminder(request, interviews)
    if download is not None:
        return download
    interview_id = request.POST.get("interview_id") or request.GET.get("edit")
    interview = get_object_or_404(interviews, pk=interview_id) if interview_id else None
    form = CandidateInterviewForm(request.POST or None, instance=interview)
    if request.method == "POST" and interview is not None and form.is_valid():
        candidate_notes = form.cleaned_data["candidate_notes"]
        interview.candidate_notes = candidate_notes
        requested_start = form.cleaned_data.get("requested_start")
        requested_end = form.cleaned_data.get("requested_end")
        if requested_start:
            interview.proposed_start = requested_start
            interview.proposed_end = requested_end
            interview.reschedule_status = "pending"
            interview.reschedule_requested_by = request.user
            interview.reschedule_reason = form.cleaned_data.get("reschedule_reason", "")
            interview.reschedule_message = "The candidate requested a new interview time."
            notify(
                interview.application.job.created_by,
                "Interview reschedule requested",
                f"{request.user.username} requested a new time for {interview.application.job.title}. Reason: {interview.reschedule_reason or 'No reason provided.'}",
                "interview",
            )
            notify(request.user, "Interview request sent", f"Your reschedule request for {interview.application.job.title} was sent to the recruiter.", "interview")
        else:
            notify(request.user, "Interview notes saved", f"Your notes for {interview.application.job.title} were saved.", "interview")
        interview.save(update_fields=[
            "candidate_notes",
            "proposed_start",
            "proposed_end",
            "reschedule_status",
            "reschedule_requested_by",
            "reschedule_message",
            "reschedule_reason",
        ])
        return redirect("candidate_calendar")
    calendar_data = build_month_calendar(interviews, request.GET.get("month"), request.GET.get("date"))
    now = timezone.now()
    return render(request, "candidates/calendar.html", _context(
        request,
        interviews=interviews,
        upcoming_interviews=interviews.filter(scheduled_start__gte=now),
        past_interviews=interviews.filter(scheduled_start__lt=now),
        form=form,
        editing_interview=interview,
        editor_open=bool(interview_id or request.GET.get("create") or request.GET.get("application") or request.method == "POST"),
        calendar=calendar_data,
        calendar_changed=calendar_changed,
    ))
