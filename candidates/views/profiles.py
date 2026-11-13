"""Candidate profile editing and resume autofill."""

from ..services import merge_completed_certifications
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from accounts.models import UserProfile
from accounts.notification_helpers import notify
from accounts.choices import (
    CAREER_CHOICES,
    CAREER_INTERESTS_BY_AREA,
    CAREER_INTEREST_CHOICES,
    PHONE_COUNTRY_CODE_CHOICES,
    SPECIALISATION_CHOICES,
    SPECIALISATIONS_BY_AREA,
    choices_for_career,
)
from accounts.decorators import candidate_required
from ..forms import CandidateProfileForm
from ..resume_parser import assess_resume_suitability
from ..services import autofill_from_resume, sync_candidate_profile
from .common import _context, _completion_percent


def _sync_main_resume(user):
    """Keep the candidate's editable main resume aligned with saved profile data."""
    from resumes.models import TailoredResume
    from resumes.services import build_profile_resume

    content = build_profile_resume(user)
    profile_resume = TailoredResume.objects.filter(
        candidate=user,
        job__isnull=True,
        title="My resume",
    ).first()
    if profile_resume:
        if profile_resume.content != content:
            profile_resume.content = content
            profile_resume.save(update_fields=["content", "updated_at"])
        return profile_resume
    return TailoredResume.objects.create(
        candidate=user,
        title="My resume",
        content=content,
        is_main=not TailoredResume.objects.filter(candidate=user, is_main=True).exists(),
    )


def _profile_initial(request, profile):
    data = merge_completed_certifications(request.user, profile.profile_data)
    stored_phone = str(data.get("phone", "") or "").strip()
    phone_country_code = data.get("phone_country_code", "") or "+65"
    phone_number = stored_phone
    if stored_phone.startswith(phone_country_code):
        phone_number = stored_phone[len(phone_country_code):].strip()
    elif not data.get("phone_country_code"):
        for code, _label in sorted(PHONE_COUNTRY_CODE_CHOICES, key=lambda item: len(item[0]), reverse=True):
            if stored_phone.startswith(code):
                phone_country_code = code
                phone_number = stored_phone[len(code):].strip()
                break
    return {
        "name": data.get("name", ""),
        "email": request.user.email,
        "phone_country_code": phone_country_code,
        "phone": phone_number,
        "career": data.get("career", ""),
        "specialisation": data.get("specialisation", ""),
        "career_stage": data.get("career_stage", ""),
        "career_interests": data.get("career_interests", []),
        "education": data.get("education", ""),
        "institution": data.get("institution", data.get("school", "")),
        "experience": data.get("experience", ""),
        "experience_entries": data.get("experience_entries", []),
        "certifications": data.get("certifications", ""),
        "certification_entries": data.get("certification_entries", []),
        "skills": data.get("skills", ""),
        "portfolio": data.get("portfolio", data.get("portfolio_links", "")),
        "awards": data.get("awards", ""),
        "linkedin": data.get("linkedin", data.get("linkedin_url", "")),
        "visa": data.get("visa", data.get("visa_status", "")),
    }


@candidate_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": "candidate"})
    merged_profile_data = merge_completed_certifications(request.user, profile.profile_data)
    if merged_profile_data != profile.profile_data:
        profile.profile_data = merged_profile_data
        profile.save(update_fields=["profile_data"])
    initial = _profile_initial(request, profile)
    form = CandidateProfileForm(request.POST or None, request.FILES or None, initial=initial)
    save_action = request.POST.get("action") if request.method == "POST" else ""
    is_autosave = save_action == "autosave"
    is_auto_upload = save_action == "auto_upload"
    is_async_save = is_autosave or is_auto_upload
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "save")
        if action == "autofill":
            uploaded_resume = form.cleaned_data.get("resume")
            source = uploaded_resume or profile.resume
            if not source:
                messages.error(request, "Upload a resume first, then use auto-fill.")
            else:
                data = dict(profile.profile_data or {})
                updates, extracted_text = autofill_from_resume(source, data)
                suitable, reason = assess_resume_suitability(extracted_text)
                if suitable:
                    if uploaded_resume:
                        profile.resume = uploaded_resume
                        profile.save(update_fields=["resume"])
                    data.update(updates)
                    data["resume"] = profile.resume.name
                    profile.profile_data = data
                    profile.save(update_fields=["profile_data"])
                    sync_candidate_profile(request.user, data)
                    _sync_main_resume(request.user)
                    notify(request.user, "Profile auto-filled", f"Sandy auto-filled {len(updates)} profile field(s) from your resume.", "profile")
                else:
                    messages.error(request, reason)
            return redirect("candidate_profile")
        data = dict(profile.profile_data or {})
        changed_fields = ["profile_data"]
        for field in form.fields:
            value = form.cleaned_data.get(field)
            if field == "resume":
                if value and not is_autosave:
                    profile.resume = value
                    changed_fields.append("resume")
                    data["resume"] = profile.resume.name
            elif field == "profile_photo":
                if value and not is_autosave:
                    profile.profile_photo = value
                    changed_fields.append("profile_photo")
            elif field == "email":
                request.user.email = value or ""
                request.user.save(update_fields=["email"])
            elif value is not None:
                data[field] = value
        phone_number = str(data.get("phone", "") or "").strip()
        phone_country_code = str(data.get("phone_country_code", "") or "").strip()
        data["phone"] = f"{phone_country_code} {phone_number}".strip() if phone_number else ""
        profile.profile_data = data
        profile.save(update_fields=changed_fields)
        sync_candidate_profile(request.user, data)
        _sync_main_resume(request.user)
        if is_async_save:
            message = "File uploaded and all changes saved" if is_auto_upload else "All changes saved automatically"
            required_fields = ("name", "career", "specialisation")
            missing_required = [field for field in required_fields if not str(data.get(field, "")).strip()]
            return JsonResponse({
                "ok": True,
                "message": message,
                "application_ready": not missing_required,
                "missing_required": missing_required,
                "saved_required": {field: data.get(field, "") for field in required_fields},
            })
        notify(request.user, "Profile updated", "Your SkillBridge profile has been updated successfully.", "profile")
        profile.refresh_from_db()
        form = CandidateProfileForm(initial=_profile_initial(request, profile))
    elif is_async_save:
        return JsonResponse({
            "ok": False,
            "message": "Some changes could not be saved. Check the highlighted fields.",
            "errors": form.errors.get_json_data(),
        }, status=400)
    career_choice_map = {
        career_area: {
            "label": dict(CAREER_CHOICES).get(career_area, career_area.title()),
            "interests": choices_for_career(CAREER_INTEREST_CHOICES, CAREER_INTERESTS_BY_AREA, career_area),
            "specialisations": choices_for_career(SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, career_area),
        }
        for career_area in CAREER_INTERESTS_BY_AREA
    }
    selected_interests = form["career_interests"].value() or []
    if isinstance(selected_interests, str):
        selected_interests = [selected_interests]
    return render(request, "candidates/profile.html", {
        **_context(request),
        "form": form,
        "profile": profile,
        "completion_percent": _completion_percent(profile),
        "career_choice_map": career_choice_map,
        "selected_interests": selected_interests,
        "guided_resume": request.GET.get("guided") == "1",
    })
