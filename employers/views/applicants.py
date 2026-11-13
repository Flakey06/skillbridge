"""Applicant review and application status updates."""

from matching.ml_model import predict_suitability
from matching.services import calculate_overall_suitability
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db.models import Count, Exists, F, OuterRef, Q
from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from applications.forms import ApplicantEvaluationForm, ApplicationStatusForm
from applications.models import ApplicantEvaluation, ApplicationReviewEvent, CandidateCompanyBlacklist, Interview, JobApplication
from jobs.models import Job
from .common import _context, _recruiter


@recruiter_required
def applicants(request):
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    recruiter = _recruiter(request)
    jobs = (
        Job.objects.filter(company=recruiter.company)
        if recruiter.company_id
        else Job.objects.filter(created_by=request.user)
    )
    company_id = recruiter.company_id or jobs.values_list("company_id", flat=True).first()
    applications = JobApplication.objects.filter(job__in=jobs).select_related("candidate", "job", "evaluation")
    applications = applications.annotate(
        company_application_count=Count(
            "candidate__job_applications",
            filter=Q(candidate__job_applications__job__company_id=company_id),
            distinct=True,
        ),
        company_rejection_count=Count(
            "candidate__job_applications",
            filter=Q(
                candidate__job_applications__job__company_id=company_id,
                candidate__job_applications__status="rejected",
            ),
            distinct=True,
        ),
        is_blacklisted=Exists(
            CandidateCompanyBlacklist.objects.filter(
                company_id=company_id, candidate_id=OuterRef("candidate_id")
            )
        ),
    )
    job_id = request.GET.get("job")
    status = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    candidate_history = request.GET.get("history", "")
    minimum_ats_score = request.GET.get("min_ats_score", "")
    if job_id:
        applications = applications.filter(job_id=job_id)
    if status:
        applications = applications.filter(status=status) if status in dict(JobApplication.STATUS_CHOICES) and status != "withdrawn" else applications.none()
    if query:
        applications = applications.filter(
            Q(candidate__username__icontains=query) | Q(candidate__email__icontains=query)
        )
    if candidate_history == "repeat":
        applications = applications.filter(company_application_count__gte=2)
    elif candidate_history == "repeat_rejections":
        applications = applications.filter(company_rejection_count__gte=2)
    elif candidate_history == "blacklisted":
        applications = applications.filter(is_blacklisted=True)
    if minimum_ats_score.isdigit():
        applications = applications.filter(match_score__gte=int(minimum_ats_score))

    sort = "match" if request.GET.get("sort") == "match" and request.user.profile.is_pro else "newest"
    if sort == "match":
        applications = applications.order_by(F("match_score").desc(nulls_last=True), "-created_at", "-pk")

    if request.method == "POST":
        application = get_object_or_404(applications, pk=request.POST.get("application_id"))
        previous_status = application.status
        status_form = ApplicationStatusForm(request.POST, instance=application)
        if status_form.is_valid():
            status_form.save()
            if previous_status != application.status:
                ApplicationReviewEvent.objects.create(
                    application=application,
                    reviewer=request.user,
                    previous_status=previous_status,
                    new_status=application.status,
                    note=request.POST.get("review_note", "").strip(),
                )
            notify(
                application.candidate,
                "Application status updated",
                f"Your application for {application.job.title} is now {application.get_status_display()}.",
                "application",
            )
            if application.candidate.email:
                send_mail(
                    subject=f"Application update for {application.job.title}",
                    message=f"Your application status is now: {application.get_status_display()}.",
                    from_email="noreply@skillbridge.local",
                    recipient_list=[application.candidate.email],
                    fail_silently=True,
                )
            messages.success(request, "Applicant status updated.")
            if previous_status != "shortlisted" and application.status == "shortlisted":
                messages.info(request, "Candidate shortlisted. Schedule the interview and confirm how you will contact them.")
                return redirect(f"{reverse('recruiter_calendar')}?application={application.pk}")
            return redirect("recruiter_applicants")
    else:
        status_form = ApplicationStatusForm()
    for application in applications:
        application.status_form = ApplicationStatusForm(instance=application)
    if has_pro:
        for application in applications:
            application.ml_prediction = predict_suitability(application.candidate, application.job)
            application.overall_score = calculate_overall_suitability(
                application.match_score,
                application.ml_prediction["score"],
            )
    return render(request, "employers/applicants.html", _context(request, applications=applications, jobs=jobs, status_form=status_form, status_choices=[(value, label) for value, label in JobApplication.STATUS_CHOICES if value != "withdrawn"], sort=sort, has_pro=has_pro, history_filter=candidate_history, minimum_ats_score=minimum_ats_score))


@recruiter_required
def applicant_detail(request, application_id):
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    application = get_object_or_404(
        JobApplication.objects.select_related("candidate", "job__company"),
        pk=application_id,
        job__created_by=request.user,
    )
    recruiter = _recruiter(request)
    company_applications = JobApplication.objects.filter(
        candidate=application.candidate,
        job__company=application.job.company,
    ).select_related("job").order_by("-created_at")
    company_application_count = company_applications.count()
    company_rejection_count = company_applications.filter(status="rejected").count()
    company_interviews = Interview.objects.filter(
        application__candidate=application.candidate,
        application__job__company=application.job.company,
    )
    company_no_show_count = company_interviews.filter(attendance_status="no_show").count()
    serious_concerns = company_interviews.filter(serious_concern=True).select_related("application__job").order_by("-scheduled_start")
    blacklist_eligible = company_no_show_count >= 2 or serious_concerns.exists()
    blacklist_entry = CandidateCompanyBlacklist.objects.filter(
        company=application.job.company,
        candidate=application.candidate,
    ).first()
    evaluation = ApplicantEvaluation.objects.filter(application=application).first()
    candidate_profile = getattr(application.candidate, "candidate_profile", None)
    profile = getattr(application.candidate, "profile", None)
    ml_prediction = predict_suitability(application.candidate, application.job) if has_pro else None
    overall_score = calculate_overall_suitability(
        application.match_score,
        ml_prediction["score"] if ml_prediction else None,
    )
    if request.method == "POST" and request.POST.get("action") == "blacklist":
        reason = request.POST.get("blacklist_reason", "").strip()
        if blacklist_entry:
            messages.info(request, "This candidate is already permanently blacklisted for your company.")
        elif not blacklist_eligible:
            messages.error(request, "Permanent blacklisting is available after two interview no-shows or a documented serious interview concern.")
        elif not reason:
            messages.error(request, "Enter a reason before permanently blacklisting this candidate.")
        else:
            CandidateCompanyBlacklist.objects.create(
                company=recruiter.company,
                candidate=application.candidate,
                blocked_by=request.user,
                reason=reason,
            )
            messages.success(request, "Candidate permanently blacklisted from applying to this company.")
        return redirect(reverse("recruiter_applicant_detail", kwargs={"application_id": application.id}) + "#candidate-history")
    if request.method == "POST" and request.POST.get("action") == "save_evaluation":
        evaluation_form = ApplicantEvaluationForm(request.POST, instance=evaluation)
        if evaluation_form.is_valid():
            evaluation = evaluation_form.save(commit=False)
            evaluation.application = application
            evaluation.reviewed_by = request.user
            evaluation.save()
            messages.success(request, f"Recruiter evaluation saved with a fixed score of {evaluation.total_score}/100.")
            return redirect(reverse("recruiter_applicant_detail", kwargs={"application_id": application.id}) + "#ats-evaluation")
    else:
        evaluation_form = ApplicantEvaluationForm(instance=evaluation)
    previous_status = application.status
    status_form = ApplicationStatusForm(request.POST or None, instance=application)
    if request.method == "POST" and status_form.is_valid():
        status_form.save()
        if previous_status != application.status:
            ApplicationReviewEvent.objects.create(
                application=application,
                reviewer=request.user,
                previous_status=previous_status,
                new_status=application.status,
                note=request.POST.get("review_note", "").strip(),
            )
        notify(
            application.candidate,
            "Application status updated",
            f"Your application for {application.job.title} is now {application.get_status_display()}.",
            "application",
        )
        messages.success(request, "Applicant status updated.")
        if previous_status != "shortlisted" and application.status == "shortlisted":
            messages.info(request, "Candidate shortlisted. Schedule the interview and confirm how you will contact them.")
            return redirect(f"{reverse('recruiter_calendar')}?application={application.pk}")
        return redirect(reverse("recruiter_applicant_detail", kwargs={"application_id": application.id}) + "#update-progress")
    return render(
        request,
        "employers/applicant_detail.html",
        _context(
            request,
            application=application,
            candidate_profile=candidate_profile,
            profile=profile,
            status_form=status_form,
            has_pro=has_pro,
            ml_prediction=ml_prediction,
            overall_score=overall_score,
            company_applications=company_applications,
            company_application_count=company_application_count,
            company_rejection_count=company_rejection_count,
            company_no_show_count=company_no_show_count,
            serious_concerns=serious_concerns,
            blacklist_eligible=blacklist_eligible,
            review_history=ApplicationReviewEvent.objects.filter(
                application__candidate=application.candidate,
                application__job__company=application.job.company,
            ).select_related("application__job", "reviewer"),
            blacklist_entry=blacklist_entry,
            evaluation=evaluation,
            evaluation_form=evaluation_form,
        ),
    )
