"""Resume review and career-interest tailoring."""

from django.contrib import messages
from django.shortcuts import redirect, render
from accounts.notification_helpers import notify
from accounts.decorators import candidate_required
from ..career_paths import (
    CAREER_FIT_PROFILES,
    CAREER_PATHS,
    _candidate_source,
    _skill_matches,
    resume_fit_matrix,
)
from ..resume_parser import extract_resume_text, review_resume
from resumes.models import TailoredResume
from resumes.services import build_interest_tailored_resume
from .common import _current_profile, _selected_career_interests, _context


@candidate_required
def resume(request):
    profile = getattr(request.user, "profile", None)
    data = (profile.profile_data if profile else {}) or {}
    feedback = None
    fit_matrix = resume_fit_matrix(request.user, _selected_career_interests(data))
    tailored_drafts = {
        draft.title: draft
        for draft in TailoredResume.objects.filter(candidate=request.user)
    }
    main_resume = TailoredResume.objects.filter(candidate=request.user, is_main=True).first()
    for fit in fit_matrix:
        draft = tailored_drafts.get(f"Resume for {fit['label']}")
        fit["tailored_resume_id"] = draft.id if draft else ""
    if profile and profile.resume:
        with profile.resume.open("rb") as resume_file:
            feedback = review_resume(extract_resume_text(resume_file))
    return render(request, "candidates/resume.html", _context(
        request,
        profile=profile,
        profile_data=data,
        feedback=feedback,
        fit_matrix=fit_matrix,
        main_resume=main_resume,
    ))


@candidate_required
def tailor_resume_for_interest(request, interest):
    profile = _current_profile(request)
    data = (profile.profile_data if profile else {}) or {}
    if interest not in _selected_career_interests(data):
        messages.error(request, "Select this career direction in your profile before tailoring a resume.")
        return redirect("candidate_resume")
    path = CAREER_PATHS.get(interest) or CAREER_FIT_PROFILES.get(interest)
    if not path:
        messages.error(request, "This career direction is not available for tailoring yet.")
        return redirect("candidate_resume")
    source, _ = _candidate_source(request.user)
    tracked_skills = path["skills"] if path else []
    matched = [skill for skill in tracked_skills if _skill_matches(source, skill)]
    skill_questions = [
        {"name": skill, "already_matched": skill in matched}
        for skill in tracked_skills
    ]
    if request.method == "POST":
        skill_evidence = {}
        errors = []
        if not request.POST.get("skip_missing"):
            for skill in tracked_skills:
                description = request.POST.get(f"description_{skill}", "").strip()
                duration = request.POST.get(f"duration_{skill}", "").strip()
                question = next(item for item in skill_questions if item["name"] == skill)
                question.update(description=description, duration=duration)
                if bool(description) != bool(duration):
                    errors.append(f"For {skill}, provide both your experience and duration, or leave both blank and follow the learning route.")
                if description and duration:
                    skill_evidence[skill] = {"description": description, "duration": duration}
        if errors:
            return render(
                request,
                "candidates/tailor_interest.html",
                _context(request, interest=interest, path=path, skill_questions=skill_questions, errors=errors),
            )
        draft = TailoredResume.objects.create(
            candidate=request.user,
            title=f"Resume for {path['label'] if path else interest.replace('-', ' ').title()}",
            content=build_interest_tailored_resume(request.user, interest, skill_evidence),
        )
        notify(request.user, "Tailored resume ready", f"Your {path['label']} resume draft is ready to review and edit.", "resume")
        return redirect("resume_detail", resume_id=draft.id)
    return render(request, "candidates/tailor_interest.html", _context(
        request, interest=interest, path=path, skill_questions=skill_questions, errors=[],
    ))
