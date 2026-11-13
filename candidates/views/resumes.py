"""Resume review and career-interest tailoring."""

from accounts.choices import CAREER_CHOICES, CAREER_INTEREST_CHOICES, CAREER_STAGE_CHOICES, EDUCATION_CHOICES, INSTITUTION_CHOICES, SPECIALISATION_CHOICES
from ..services import merge_completed_certifications
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
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
from resumes.services import build_interest_tailored_resume, build_profile_resume
from .common import _current_profile, _selected_career_interests, _career_interest_labels, _context


def _resume_timeline(user):
    timeline = []
    for draft in TailoredResume.objects.filter(candidate=user).select_related("job", "job__company"):
        if draft.job_id:
            category = "Job application"
        elif draft.title == "My resume":
            category = "Main profile resume"
        elif draft.title.startswith("Resume for "):
            category = "Career direction"
        else:
            category = "General draft"
        updated_at = timezone.localtime(draft.updated_at)
        timeline.append({
            "resume": draft,
            "category": category,
            "version": updated_at.strftime("v%Y.%m.%d-%H%M"),
            "updated_at": updated_at,
        })
    return timeline


@candidate_required
def resume(request):
    profile = _current_profile(request)
    main_resume = TailoredResume.objects.filter(candidate=request.user, is_main=True).first()
    if main_resume and not main_resume.job_id and main_resume.title == "My resume":
        profile_content = build_profile_resume(request.user)
        if main_resume.content != profile_content:
            main_resume.content = profile_content
            main_resume.save(update_fields=["content", "updated_at"])
    if request.method == "POST" and request.POST.get("action") == "edit_resume":
        selected_resume = TailoredResume.objects.filter(
            candidate=request.user,
            pk=request.POST.get("resume_id"),
        ).first()
        if not selected_resume:
            selected_resume = main_resume
        if not selected_resume:
            selected_resume = TailoredResume.objects.create(
                candidate=request.user,
                title="My resume",
                content=build_profile_resume(request.user),
                is_main=True,
            )
        return redirect("resume_detail", resume_id=selected_resume.id)
    data = merge_completed_certifications(
        request.user,
        profile.profile_data if profile else {},
    )
    resume_data = dict(data)
    resume_data["email"] = request.user.email
    resume_data["career_label"] = dict(CAREER_INTEREST_CHOICES).get(
        data.get("career"),
        dict(CAREER_CHOICES).get(data.get("career"), data.get("career", "")),
    )
    resume_data["specialisation_label"] = dict(SPECIALISATION_CHOICES).get(
        data.get("specialisation"),
        data.get("specialisation", ""),
    )
    resume_data["education_label"] = dict(EDUCATION_CHOICES).get(
        data.get("education"),
        data.get("education", ""),
    )
    resume_data["institution_label"] = dict(INSTITUTION_CHOICES).get(
        data.get("institution"),
        data.get("institution", ""),
    )
    resume_data["career_stage_label"] = dict(CAREER_STAGE_CHOICES).get(
        data.get("career_stage"),
        data.get("career_stage", ""),
    )
    resume_data["career_interest_labels"] = _career_interest_labels(
        _selected_career_interests(data)
    )
    certificate_entries = list(resume_data.get("completed_career_certificates", []))
    existing_certifications = str(resume_data.get("certifications", "") or "").strip()
    certification_lines = [line.strip() for line in existing_certifications.splitlines() if line.strip()]
    for certificate in certificate_entries:
        title = certificate.get("title", "").strip()
        certificate_id = certificate.get("certificate_id", "").strip()
        if not title:
            continue
        line = f"{title} (Certificate ID: {certificate_id})" if certificate_id else title
        if line not in certification_lines:
            certification_lines.append(line)
    resume_data["certifications"] = "\n".join(certification_lines)
    feedback = None
    fit_matrix = resume_fit_matrix(request.user, _selected_career_interests(data))
    tailored_drafts = {
        draft.title: draft
        for draft in TailoredResume.objects.filter(candidate=request.user)
    }
    resume_timeline = _resume_timeline(request.user)
    for fit in fit_matrix:
        draft = tailored_drafts.get(f"Resume for {fit['label']}")
        fit["tailored_resume_id"] = draft.id if draft else ""
    if profile and profile.resume:
        with profile.resume.open("rb") as resume_file:
            feedback = review_resume(extract_resume_text(resume_file))
    return render(request, "candidates/resume.html", _context(
        request,
        profile=profile,
        profile_data=resume_data,
        feedback=feedback,
        fit_matrix=fit_matrix,
        main_resume=main_resume,
        resume_timeline=resume_timeline,
    ))


@candidate_required
def choose_resume_to_edit(request):
    main_resume = TailoredResume.objects.filter(candidate=request.user, is_main=True).first()
    if not TailoredResume.objects.filter(candidate=request.user).exists():
        main_resume = TailoredResume.objects.create(
            candidate=request.user,
            title="My resume",
            content=build_profile_resume(request.user),
            is_main=True,
        )
    timeline = _resume_timeline(request.user)
    selected_id = request.GET.get("resume_id")
    selected_resume = TailoredResume.objects.filter(
        candidate=request.user,
        pk=selected_id,
    ).first()
    if not selected_resume:
        selected_resume = main_resume or timeline[0]["resume"]
    selected_item = next(
        (item for item in timeline if item["resume"].pk == selected_resume.pk),
        None,
    )
    return render(request, "candidates/resume_select.html", _context(
        request,
        resume_timeline=timeline,
        selected_resume=selected_resume,
        selected_item=selected_item,
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
