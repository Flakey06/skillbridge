from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import candidate_required
from accounts.notification_helpers import notify
from applications.forms import ApplicationForm
from applications.models import JobApplication, SavedJob
from matching.services import calculate_overall_suitability, get_or_update_match
from matching.ml_model import predict_suitability
from resumes.models import TailoredResume
from resumes.services import build_tailored_cover_letter, build_tailored_resume

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
    job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)
    application = JobApplication.objects.filter(candidate=request.user, job=job).first()
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
            if profile_missing_fields:
                messages.warning(
                    request,
                    "Please complete your name, career area, and specialisation before applying.",
                )
            elif form.is_valid():
                if not tailored_draft:
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
                if not tailored_draft.approved_at:
                    messages.warning(
                        request,
                        "Please review and approve your tailored resume before submitting.",
                    )
                    return redirect("resume_detail", resume_id=tailored_draft.id)
                application = form.save(commit=False)
                application.candidate = request.user
                application.job = job
                application.match_score = match.score
                application.matched_skills = match.matched_skills
                application.missing_skills = match.missing_skills
                application.match_breakdown = match.score_breakdown
                application.match_assessment = match.assessment
                main_resume = TailoredResume.objects.filter(
                    candidate=request.user,
                    is_main=True,
                ).first()
                application.tailored_resume = (
                    main_resume.clean_content
                    if main_resume
                    else build_tailored_resume(request.user, job)
                )
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
        },
    )
