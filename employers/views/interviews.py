"""Recruiter interview transcription, notes, and evaluation workspace."""

import re

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
    if request.method == "POST" and request.POST.get("action") == "autosave_notes":
        interview.notes = request.POST.get("notes", "")[:10000]
        interview.transcript = request.POST.get("transcript", "")[:50000]
        interview.summary = request.POST.get("summary", "")[:10000]
        interview.save(update_fields=["notes", "transcript", "summary"])
        return JsonResponse({"ok": True, "message": "Interview notes saved"})

    if request.method == "POST" and request.POST.get("action") == "generate_summary":
        transcript = request.POST.get("transcript", "")[:50000].strip()
        notes = request.POST.get("notes", "")[:10000].strip()
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", transcript) if item.strip()]
        summary_parts = sentences[:5]
        if notes:
            summary_parts.append(f"Recruiter notes: {notes}")
        summary = " ".join(summary_parts)[:10000]
        if not summary:
            return JsonResponse({"ok": False, "message": "Add a transcript or notes before generating a summary."}, status=400)
        interview.transcript = transcript
        interview.notes = notes
        interview.summary = summary
        interview.save(update_fields=["transcript", "notes", "summary"])
        return JsonResponse({"ok": True, "summary": summary, "message": "Summary generated and saved"})

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
    ))
