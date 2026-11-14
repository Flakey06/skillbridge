"""Recruiter live interview workspace."""

from urllib.parse import urlparse
from uuid import uuid4

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.decorators import recruiter_required
from applications.forms import ApplicantEvaluationForm
from applications.models import ApplicantEvaluation, Interview

from .common import _context


@recruiter_required
def interview_workspace(request, interview_id):
    interview = get_object_or_404(
        Interview.objects.select_related("application__candidate__profile", "application__job__company"),
        pk=interview_id,
        application__job__created_by=request.user,
    )
    application = interview.application
    evaluation = ApplicantEvaluation.objects.filter(application=application).first()
    meeting_url = interview.meeting_url
    if not meeting_url and interview.contact_method == "video" and interview.contact_details.startswith(("https://", "http://")):
        meeting_url = interview.contact_details
    if not meeting_url and interview.contact_method == "video":
        meeting_url = f"https://meet.jit.si/skillbridge-{uuid4().hex}"
        interview.meeting_url = meeting_url
        interview.save(update_fields=["meeting_url"])
    meeting_host = (urlparse(meeting_url).hostname or "").casefold() if meeting_url else ""
    meeting_provider = "Video call"
    if meeting_host in {"meet.jit.si", "www.meet.jit.si"}:
        meeting_provider = "Jitsi Meet"
    elif meeting_host in {"meet.google.com", "www.meet.google.com"}:
        meeting_provider = "Google Meet"
    elif meeting_host.endswith("zoom.us"):
        meeting_provider = "Zoom"
    elif meeting_host in {"teams.microsoft.com", "www.teams.microsoft.com"}:
        meeting_provider = "Microsoft Teams"
    meeting_embed_url = meeting_url if meeting_host in {"meet.jit.si", "www.meet.jit.si"} else ""

    if request.method == "POST" and request.POST.get("action") == "autosave_notes":
        interview.notes = request.POST.get("notes", "")[:10000]
        interview.transcript = request.POST.get("transcript", "")[:50000]
        interview.summary = request.POST.get("summary", "")[:10000]
        interview.save(update_fields=["notes", "transcript", "summary"])
        return JsonResponse({"ok": True, "message": "Interview notes saved"})

    if request.method == "POST" and request.POST.get("action") == "save_evaluation":
        evaluation_form = ApplicantEvaluationForm(request.POST, instance=evaluation)
        if evaluation_form.is_valid():
            evaluation = evaluation_form.save(commit=False)
            evaluation.application = application
            evaluation.reviewed_by = request.user
            evaluation.save()
            messages.success(request, f"Recruiter evaluation saved: {evaluation.total_score}/100.")
            return redirect(reverse("recruiter_interview_workspace", args=[interview.pk]) + "#interview-rating")
    else:
        evaluation_form = ApplicantEvaluationForm(instance=evaluation)

    return render(request, "employers/interview_workspace.html", _context(
        request,
        interview=interview,
        application=application,
        profile=application.candidate.profile,
        evaluation=evaluation,
        evaluation_form=evaluation_form,
        meeting_url=meeting_url,
        meeting_provider=meeting_provider,
        meeting_embed_url=meeting_embed_url,
    ))
