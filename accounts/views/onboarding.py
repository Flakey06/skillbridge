"""Onboarding questionnaire, resume upload, and draft endpoints."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from ..choices import (
    CAREER_CHOICES,
    CAREER_INTERESTS_BY_AREA,
    CAREER_INTEREST_CHOICES,
    SPECIALISATION_CHOICES,
    SPECIALISATIONS_BY_AREA,
    choices_for_career,
)
from ..forms import OnboardingForm
from ..notification_helpers import notify
from .common import _role, _profile
from .onboarding_helpers import (
    CANDIDATE_STEPS,
    RECRUITER_STEPS,
    _step_value,
    _next_step,
    _finish_onboarding,
    _resume_form_initial,
    _save_resume_form,
)


@login_required
def onboarding(request):
    role = _role(request)
    steps = RECRUITER_STEPS if role == "recruiter" else CANDIDATE_STEPS
    profile = _profile(request)
    answers = dict(profile.profile_data or {})
    answers.update(request.session.get("onboarding_answers", {}))
    step_number = int(request.session.get("onboarding_step", _next_step(profile, steps)))
    if step_number >= len(steps):
        return _finish_onboarding(request)
    step = dict(steps[step_number])
    show_sandy_intro = step_number == 0 and not request.session.get("sandy_intro_seen", False)
    if show_sandy_intro:
        request.session["sandy_intro_seen"] = True
    career_area = answers.get("career", "")
    if step["id"] == "career_interests":
        step["choices"] = choices_for_career(CAREER_INTEREST_CHOICES, CAREER_INTERESTS_BY_AREA, career_area)
    elif step["id"] == "specialisation":
        step["choices"] = choices_for_career(SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, career_area)
    initial = {} if step.get("type") == "file" else {
        step["id"]: answers.get(step["id"], [] if step.get("type") == "multi" else "")
    }
    form = OnboardingForm(
        request.POST or None,
        request.FILES or None,
        initial=initial,
        field_name=step["id"],
        label=step["label"],
        field_type=step.get("type", "text"),
        choices=step.get("choices"),
        required=step.get("required", True),
    )
    resume_form = None
    if role == "candidate" and step["id"] == "resume":
        from candidates.forms import CandidateProfileForm
        resume_form = CandidateProfileForm(
            request.POST or None, request.FILES or None,
            initial=_resume_form_initial(request, profile, answers),
        )
        if request.method == "POST" and len(request.FILES.getlist("resume")) > 1:
            resume_form.is_valid()
            resume_form.add_error("resume", "Upload only one resume at a time.")
    if request.method == "POST" and request.POST.get("back") == "1":
        request.session["onboarding_step"] = max(0, step_number - 1)
        return redirect("onboarding")
    if request.method == "POST" and request.POST.get("skip") == "1":
        return _finish_onboarding(request)
    if request.method == "POST" and step["id"] == "resume" and resume_form and resume_form.is_valid():
        action = request.POST.get("action", "save_resume")
        uploaded_resume = resume_form.cleaned_data.get("resume")
        if action == "extract_resume":
            if profile.resume:
                resume_form.add_error("resume", "Delete the current resume before uploading another one.")
            elif not uploaded_resume:
                resume_form.add_error("resume", "Choose a resume file to upload first.")
            else:
                from candidates.services import autofill_from_resume, sync_candidate_profile
                from candidates.resume_parser import assess_resume_suitability
                updates, extracted_text = autofill_from_resume(uploaded_resume, answers)
                is_suitable, rejection_reason = assess_resume_suitability(extracted_text)
                if is_suitable:
                    profile.resume = uploaded_resume
                    profile.save(update_fields=["resume"])
                    answers.update(updates)
                    answers["resume"] = profile.resume.name
                    profile.profile_data = answers
                    profile.save(update_fields=["profile_data"])
                    sync_candidate_profile(request.user, answers)
                    request.session["onboarding_answers"] = answers
                    request.session["onboarding_step"] = step_number
                    request.session["sandy_intro_seen"] = True
                    notify(request.user, "Resume submitted", "Sandy auto-filled your guided profile fields. Review and edit them before continuing.", "profile")
                    return redirect("onboarding")
                resume_form.add_error("resume", rejection_reason)
        else:
            _save_resume_form(request, profile, resume_form, answers)
            request.session["onboarding_answers"] = answers
            request.session["onboarding_step"] = step_number + 1
            notify(request.user, "Resume profile saved", "Your resume profile was saved and the preview has been updated.", "profile")
            return redirect("onboarding")
    elif request.method == "POST" and step["id"] != "resume" and form.is_valid():
        value = form.cleaned_data.get(step["id"])
        if step["id"] == "resume":
            if value:
                profile.resume = value
                profile.save(update_fields=["resume"])
            answers[step["id"]] = profile.resume.name if profile.resume else ""
            if value and role == "candidate":
                from candidates.services import autofill_from_resume

                updates, _ = autofill_from_resume(value, answers)
                answers.update(updates)
        else:
            answers[step["id"]] = value
        profile.profile_data = answers
        profile.save(update_fields=["profile_data"])
        if role == "candidate":
            from candidates.services import sync_candidate_profile

            sync_candidate_profile(request.user, answers)
        request.session["onboarding_answers"] = answers
        request.session["onboarding_step"] = step_number + 1
        if step_number + 1 >= len(steps):
            return _finish_onboarding(request)
        return redirect("onboarding")
    completed_steps = []
    for item in steps[:step_number]:
        answer = _step_value(profile, answers, item) or ""
        if item["id"] == "resume" and hasattr(answer, "name"):
            answer = answer.name
        labels = dict(item.get("choices", []))
        if isinstance(answer, (list, tuple)):
            answer_display = ", ".join(labels.get(value, value) for value in answer)
        else:
            answer_display = labels.get(answer, answer)
        completed_steps.append({
            **item,
            "answer": answer,
            "answer_display": answer_display,
        })
    career_choice_map = {
        area: {
            "interests": choices_for_career(CAREER_INTEREST_CHOICES, CAREER_INTERESTS_BY_AREA, area),
            "specialisations": choices_for_career(SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, area),
        }
        for area, _label in CAREER_CHOICES
    }
    display_steps = steps
    return render(request, "accounts/onboarding.html", {"role": role, "profile": profile, "steps": display_steps, "step": step, "step_number": step_number, "answers": answers, "completed_steps": completed_steps, "form": form, "resume_form": resume_form, "show_sandy_intro": show_sandy_intro, "career_choice_map": career_choice_map, "total_steps": len(display_steps)})


@login_required
@require_POST
def scan_resume_upload(request):
    if _role(request) != "candidate":
        return JsonResponse({"ok": False, "error": "Candidate account required."}, status=403)
    uploads = request.FILES.getlist("resume")
    if len(uploads) != 1:
        return JsonResponse({"ok": False, "error": "Upload exactly one resume."}, status=400)
    profile = _profile(request)
    if profile.resume:
        return JsonResponse({"ok": False, "error": "Delete the current resume before uploading another one."}, status=409)
    upload = uploads[0]
    from django.core.exceptions import ValidationError
    from candidates.forms import validate_resume_upload
    from candidates.resume_parser import assess_resume_suitability
    from candidates.services import autofill_from_resume, sync_candidate_profile
    try:
        validate_resume_upload(upload)
    except ValidationError as error:
        return JsonResponse({"ok": False, "error": error.messages[0]}, status=400)
    answers = dict(profile.profile_data or {})
    answers.update(request.session.get("onboarding_answers", {}))
    updates, extracted_text = autofill_from_resume(upload, answers)
    is_suitable, reason = assess_resume_suitability(extracted_text)
    if not is_suitable:
        return JsonResponse({"ok": False, "error": reason}, status=400)
    profile.resume = upload
    answers.update(updates)
    answers["resume"] = upload.name
    profile.profile_data = answers
    profile.save()
    sync_candidate_profile(request.user, answers)
    request.session["onboarding_answers"] = answers
    request.session["onboarding_step"] = 0
    return JsonResponse({"ok": True, "filename": profile.resume.name.rsplit("/", 1)[-1], "updates": updates})


@login_required
@require_POST
def delete_onboarding_resume(request):
    if _role(request) != "candidate":
        return JsonResponse({"ok": False, "error": "Candidate account required."}, status=403)
    profile = _profile(request)
    if profile.resume:
        profile.resume.delete(save=False)
    answers = dict(profile.profile_data or {})
    answers.pop("resume", None)
    profile.resume = None
    profile.profile_data = answers
    profile.save(update_fields=["resume", "profile_data"])
    request.session["onboarding_answers"] = answers
    return JsonResponse({"ok": True})


@login_required
@require_POST
def autosave_resume_draft(request):
    if _role(request) != "candidate":
        return JsonResponse({"ok": False, "error": "Candidate account required."}, status=403)
    from candidates.forms import CandidateProfileForm

    profile = _profile(request)
    answers = dict(profile.profile_data or {})
    answers.update(request.session.get("onboarding_answers", {}))
    form = CandidateProfileForm(request.POST, initial=_resume_form_initial(request, profile, answers))
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    _save_resume_form(request, profile, form, answers)
    request.session["onboarding_answers"] = answers
    return JsonResponse({"ok": True, "message": "Draft saved"})
