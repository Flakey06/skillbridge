"""Onboarding steps, completion checks, and guided profile persistence."""

from django.shortcuts import redirect
from django.utils import timezone
from ..administration_stats import ONBOARDING_COMPLETED_KEY
from .common import _profile
from employers.choices import INDUSTRY_CHOICES
from ..choices import CAREER_INTEREST_CHOICES, CAREER_STAGE_CHOICES, VISA_CHOICES


CANDIDATE_STEPS = [
    {"id": "resume", "title": "Your resume", "question": "How would you like to build your resume? Upload a PDF, DOCX, or TXT file for automatic extraction, or use our guided resume builder.", "label": "Upload resume", "type": "file", "required": False},
    {"id": "career_stage", "title": "Current level", "question": "Where are you starting from in these directions? This helps us order the roadmap; you can update it later.", "label": "Current level", "type": "select", "choices": CAREER_STAGE_CHOICES, "required": False},
    {"id": "career_interests", "title": "Skill interests", "question": "Which directions do you want to develop? You can also choose a cross-discipline subject outside your main career area.", "label": "Skill interests", "type": "multi", "choices": CAREER_INTEREST_CHOICES, "required": False},
    {"id": "visa", "title": "Work authorisation", "question": "What is your current work authorisation status? This stays in your SkillBridge profile and is not added to your resume.", "label": "Work authorisation", "type": "select", "choices": VISA_CHOICES, "required": False},
]


RECRUITER_STEPS = [
    {"id": "company", "title": "Company", "question": "What is your company called?", "label": "Company name"},
    {"id": "industry", "title": "Industry", "question": "Which industry does your company operate in?", "label": "Industry", "type": "select", "choices": INDUSTRY_CHOICES},
    {"id": "website", "title": "Company details", "question": "Where can candidates learn more about your company?", "label": "Company website"},
    {"id": "hiring_goal", "title": "Hiring goal", "question": "What kind of candidates are you hoping to find?", "label": "Hiring goal", "type": "textarea"},
]


def _step_value(profile, answers, step):
    if step["id"] == "resume":
        return profile.resume
    return answers.get(step["id"])


def _profile_is_complete(profile, steps):
    answers = profile.profile_data or {}
    return all(
        not step.get("required", True) or _step_value(profile, answers, step)
        for step in steps
    )


def _next_step(profile, steps):
    answers = profile.profile_data or {}
    for index, step in enumerate(steps):
        if not _step_value(profile, answers, step):
            return index
    return len(steps)


def _finish_onboarding(request):
    profile = _profile(request)
    data = dict(profile.profile_data or {})
    if not data.get(ONBOARDING_COMPLETED_KEY):
        data[ONBOARDING_COMPLETED_KEY] = timezone.now().isoformat()
        profile.profile_data = data
        profile.save(update_fields=['profile_data'])
    request.session["onboarding_complete"] = True
    next_url = request.session.pop("post_onboarding_next", "")
    return redirect(next_url or "home")


def _resume_form_initial(request, profile, answers):
    stored_phone = str(answers.get("phone", "") or "").strip()
    country_code = answers.get("phone_country_code", "") or "+65"
    phone = stored_phone[len(country_code):].strip() if stored_phone.startswith(country_code) else stored_phone
    return {
        "name": answers.get("name", ""), "email": answers.get("email", request.user.email),
        "phone_country_code": country_code, "phone": phone,
        "career": answers.get("career", ""), "specialisation": answers.get("specialisation", ""),
        "career_stage": answers.get("career_stage", ""), "career_interests": answers.get("career_interests", []),
        "education": answers.get("education", ""), "institution": answers.get("institution", answers.get("school", "")),
        "experience": answers.get("experience", ""), "experience_entries": answers.get("experience_entries", []),
        "certifications": answers.get("certifications", ""), "certification_entries": answers.get("certification_entries", []),
        "skills": answers.get("skills", ""), "portfolio": answers.get("portfolio", ""),
        "awards": answers.get("awards", ""), "linkedin": answers.get("linkedin", ""), "visa": answers.get("visa", ""),
    }


def _save_resume_form(request, profile, resume_form, answers):
    for field in resume_form.fields:
        value = resume_form.cleaned_data.get(field)
        if field in {"career_stage", "career_interests", "visa"} and field not in request.POST:
            continue
        if field == "resume":
            if value:
                profile.resume = value
                answers["resume"] = value.name
        elif field == "profile_photo":
            if value:
                profile.profile_photo = value
        elif field == "email":
            request.user.email = value or ""
            request.user.save(update_fields=["email"])
        elif value is not None:
            answers[field] = value
    number = str(answers.get("phone", "") or "").strip()
    code = str(answers.get("phone_country_code", "") or "").strip()
    answers["phone"] = f"{code} {number}".strip() if number else ""
    profile.profile_data = answers
    profile.save()
    from candidates.services import sync_candidate_profile
    sync_candidate_profile(request.user, answers)
