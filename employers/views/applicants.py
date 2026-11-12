"""Applicant review and application status updates."""

from matching.ml_model import predict_suitability
from matching.services import calculate_overall_suitability
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import F
from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from applications.forms import ApplicationStatusForm
from applications.models import JobApplication
from jobs.models import Job
from .common import _context


@recruiter_required
def applicants(request):
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs).select_related("candidate", "job")
    job_id = request.GET.get("job")
    status = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    if job_id:
        applications = applications.filter(job_id=job_id)
    if status:
        applications = applications.filter(status=status)
    if query:
        applications = applications.filter(candidate__username__icontains=query)

    sort = "match" if request.GET.get("sort") == "match" and request.user.profile.is_pro else "newest"
    if sort == "match":
        applications = applications.order_by(F("match_score").desc(nulls_last=True), "-created_at", "-pk")

    if request.method == "POST":
        application = get_object_or_404(applications, pk=request.POST.get("application_id"))
        status_form = ApplicationStatusForm(request.POST, instance=application)
        if status_form.is_valid():
            status_form.save()
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
    return render(request, "employers/applicants.html", _context(request, applications=applications, jobs=jobs, status_form=status_form, sort=sort, has_pro=has_pro))


@recruiter_required
def applicant_detail(request, application_id):
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    application = get_object_or_404(
        JobApplication.objects.select_related("candidate", "job__company"),
        pk=application_id,
        job__created_by=request.user,
    )
    candidate_profile = getattr(application.candidate, "candidate_profile", None)
    profile = getattr(application.candidate, "profile", None)
    ml_prediction = predict_suitability(application.candidate, application.job) if has_pro else None
    overall_score = calculate_overall_suitability(
        application.match_score,
        ml_prediction["score"] if ml_prediction else None,
    )
    status_form = ApplicationStatusForm(request.POST or None, instance=application)
    if request.method == "POST" and status_form.is_valid():
        status_form.save()
        notify(
            application.candidate,
            "Application status updated",
            f"Your application for {application.job.title} is now {application.get_status_display()}.",
            "application",
        )
        messages.success(request, "Applicant status updated.")
        return redirect("recruiter_applicant_detail", application_id=application.id)
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
        ),
    )
