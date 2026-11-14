from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import candidate_required
from accounts.notification_helpers import notify
from accounts.models import ModerationReport
import matching.services as matching_services
from applications.forms import ApplicationForm
from applications.models import CandidateCompanyBlacklist, JobApplication, SavedJob
from matching.services import calculate_overall_suitability, get_or_update_match
from matching.ml_model import predict_suitability
from resumes.models import TailoredResume
from resumes.services import _contains, _job_skills, build_tailored_cover_letter, build_tailored_resume

from .models import Job


@candidate_required
@require_POST
def save_job(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if request.POST.get("action") == "save":
        SavedJob.objects.get_or_create(candidate=request.user, job=job)
    elif request.POST.get("action") == "unsave":
        SavedJob.objects.filter(candidate=request.user, job=job).delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "job_id": job.pk,
            "is_saved": SavedJob.objects.filter(candidate=request.user, job=job).exists(),
            "saved_count": SavedJob.objects.filter(candidate=request.user).count(),
        })
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect("candidate_jobs")


@candidate_required
def detail(request, job_id):
    job = get_object_or_404(Job.objects.select_related("company"), pk=job_id, moderation_status="approved")
    application = JobApplication.objects.filter(candidate=request.user, job=job).first()
    is_blacklisted = CandidateCompanyBlacklist.objects.filter(
        candidate=request.user, company=job.company
    ).exists()
    tailored_draft = TailoredResume.objects.filter(
        candidate=request.user,
        job=job,
    ).first()
    is_saved = SavedJob.objects.filter(candidate=request.user, job=job).exists()
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    match = get_or_update_match(request.user, job) if has_pro else None
    ml_prediction = predict_suitability(request.user, job) if has_pro else None
    overall_score = calculate_overall_suitability(
        match.score if match else None,
        ml_prediction["score"] if ml_prediction else None,
    )
    form = ApplicationForm(
        request.POST or None,
        initial={"cover_note": build_tailored_cover_letter(request.user, job)},
    )
    profile = getattr(request.user, "profile", None)
    profile_data = (profile.profile_data if profile else {}) or {}
    main_resume = TailoredResume.objects.filter(candidate=request.user, is_main=True).first()
    available_resumes = []
    job_skills = _job_skills(job)
    job_text = " ".join((job.title, job.description, job.required_skills, job.preferred_skills))
    for candidate_resume in TailoredResume.objects.filter(candidate=request.user).select_related("job"):
        if candidate_resume.job_id:
            resume_type = "Job application"
        elif candidate_resume.title == "My resume":
            resume_type = "Profile resume"
        elif candidate_resume.title.startswith("Resume for "):
            resume_type = "Career direction"
        else:
            resume_type = "General draft"
        updated_at = timezone.localtime(candidate_resume.updated_at)
        matched_resume_skills = [
            skill for skill in job_skills
            if _contains(candidate_resume.clean_content, skill)
        ]
        fit_score = round(len(matched_resume_skills) / len(job_skills) * 100) if job_skills else 0
        ai_compatibility, ai_reason = matching_services.predict_ai_compatibility(
            candidate_resume.clean_content,
            job_text,
            fit_score,
        )
        recommendation_score = calculate_overall_suitability(fit_score, ai_compatibility)
        if recommendation_score >= 80:
            resume_assessment = "Strong fit"
        elif recommendation_score >= 60:
            resume_assessment = "Good foundation"
        elif recommendation_score >= 40:
            resume_assessment = "Developing fit"
        else:
            resume_assessment = "Early-stage fit"
        available_resumes.append({
            "resume": candidate_resume,
            "type": resume_type,
            "version": updated_at.strftime("v%Y.%m.%d-%H%M"),
            "fit_score": fit_score,
            "matched_skills": matched_resume_skills,
            "ai_compatibility": ai_compatibility,
            "ai_reason": ai_reason,
            "recommendation_score": recommendation_score,
            "assessment": resume_assessment,
        })
    recommended_resume = None
    if has_pro and available_resumes:
        recommended_resume = max(
            available_resumes,
            key=lambda item: (
                item["recommendation_score"],
                item["fit_score"],
                item["resume"].job_id == job.id,
                bool(item["resume"].approved_at),
                item["resume"].updated_at,
            ),
        )
        recommendation_score = recommended_resume["recommendation_score"]
        if recommendation_score >= 80:
            recommended_resume["assessment"] = "Strong fit"
        elif recommendation_score >= 60:
            recommended_resume["assessment"] = "Good foundation"
        elif recommendation_score >= 40:
            recommended_resume["assessment"] = "Developing fit"
        else:
            recommended_resume["assessment"] = "Early-stage fit"
    default_resume_id = (
        recommended_resume["resume"].id if recommended_resume
        else tailored_draft.id if tailored_draft
        else main_resume.id if main_resume
        else ""
    )
    selected_resume_id = request.POST.get("resume_id", default_resume_id)
    profile_missing_fields = [
        field
        for field in ("name", "career", "specialisation")
        if not profile_data.get(field)
    ]

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            SavedJob.objects.get_or_create(candidate=request.user, job=job)
            messages.success(request, "Job saved to your shortlist.")
            return redirect("job_detail", job_id=job.id)
        if action == "unsave":
            SavedJob.objects.filter(candidate=request.user, job=job).delete()
            messages.success(request, "Job removed from your shortlist.")
            return redirect("job_detail", job_id=job.id)
        if action == "tailor":
            draft = TailoredResume.objects.create(
                candidate=request.user,
                job=job,
                title=f"Resume for {job.title}",
                content=build_tailored_resume(request.user, job),
            )
            return redirect("resume_detail", resume_id=draft.id)
        if action == "apply" and not application:
            if is_blacklisted:
                messages.error(request, "You cannot apply to roles at this company.")
            elif profile_missing_fields:
                messages.warning(
                    request,
                    "Please complete your name, career area, and specialisation before applying.",
                )
            elif form.is_valid():
                selected_resume = None
                if selected_resume_id:
                    selected_resume = TailoredResume.objects.filter(
                        candidate=request.user,
                        pk=selected_resume_id,
                    ).first()
                if not selected_resume:
                    selected_resume = tailored_draft or main_resume
                if not selected_resume:
                    tailored_draft = TailoredResume.objects.create(
                        candidate=request.user,
                        job=job,
                        title=f"Resume for {job.title}",
                        content=build_tailored_resume(request.user, job),
                    )
                    messages.info(
                        request,
                        "Please review your tailored resume before submitting your application.",
                    )
                    return redirect("resume_detail", resume_id=tailored_draft.id)
                if not selected_resume.approved_at:
                    if request.POST.get("resume_confirmed") != "yes":
                        messages.warning(
                            request,
                            "Confirm that you reviewed the selected resume and cover letter before applying.",
                        )
                        return redirect("job_detail", job_id=job.id)
                    selected_resume.approved_at = timezone.now()
                    selected_resume.save(update_fields=["approved_at", "updated_at"])
                application = form.save(commit=False)
                application.candidate = request.user
                application.job = job
                # Persist the submission-time skill score and its separate evidence
                # breakdown. Candidate plan access only controls insight visibility.
                application_match = match or get_or_update_match(request.user, job)
                application.match_score = application_match.score
                application.matched_skills = application_match.matched_skills
                application.missing_skills = application_match.missing_skills
                application.match_breakdown = application_match.score_breakdown
                application.match_assessment = application_match.assessment
                application.tailored_resume = selected_resume.clean_content
                application.save()
                notify(
                    job.created_by,
                    "New job application",
                    f"{request.user.username} applied for {job.title}.",
                    "application",
                )
                notify(
                    request.user,
                    "Application submitted",
                    f"Your application for {job.title} has been submitted successfully.",
                    "application",
                )
                messages.success(request, "Your application has been submitted.")
                return redirect("candidate_applications")

    return render(
        request,
        "jobs/detail.html",
        {
            "role": "candidate",
            "has_pro": has_pro,
            "job": job,
            "application": application,
            "tailored_draft": tailored_draft,
            "is_saved": is_saved,
            "match": match,
            "ml_prediction": ml_prediction,
            "overall_score": overall_score,
            "form": form,
            "profile_missing_fields": profile_missing_fields,
            "main_resume": main_resume,
            "available_resumes": available_resumes,
            "selected_resume_id": selected_resume_id,
            "recommended_resume": recommended_resume,
            "is_blacklisted": is_blacklisted,
        },
    )


@candidate_required
@require_POST
def report_job(request, job_id):
    job = get_object_or_404(Job, pk=job_id, moderation_status="approved")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Select a reason for the report.")
    else:
        ModerationReport.objects.create(
            reporter=request.user,
            subject_type="job",
            subject_id=str(job.pk),
            subject_label=str(job),
            reason=reason,
            details=request.POST.get("details", "").strip(),
        )
        messages.success(request, "Your report was sent to the moderation team.")
    return redirect("job_detail", job_id=job.pk)
