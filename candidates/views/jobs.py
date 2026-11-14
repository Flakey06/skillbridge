"""Job discovery, saved jobs, and application tracking."""

from matching.services import calculate_overall_suitability
from matching.ml_model import predict_suitability
import re

from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from accounts.decorators import candidate_required
from applications.models import JobApplication, SavedJob
from jobs.forms import JobFilterForm
from jobs.models import Job
from matching.services import get_or_update_match
from .common import _context, _current_profile


@candidate_required
def jobs(request):
    form = JobFilterForm(request.GET)
    job_queryset = Job.objects.filter(status="open", moderation_status="approved").select_related("company")
    if form.is_valid():
        query = form.cleaned_data.get("q")
        location = form.cleaned_data.get("location")
        employment_type = form.cleaned_data.get("employment_type")
        skills = Job.split_skills(form.cleaned_data.get("required_skills", ""))
        experience_level = form.cleaned_data.get("experience_level")
        salary_range = form.cleaned_data.get("salary_range")
        if query:
            job_queryset = job_queryset.filter(
                Q(title__icontains=query)
                | Q(company__name__icontains=query)
                | Q(required_skills__icontains=query)
            )
        if location:
            job_queryset = job_queryset.filter(location__icontains=location)
        if employment_type:
            job_queryset = job_queryset.filter(employment_type=employment_type)
        for skill in skills:
            job_queryset = job_queryset.filter(
                required_skills__iregex=r"(?:^|,|\n)\s*" + re.escape(skill) + r"\s*(?:,|\n|$)"
            )
        if experience_level:
            job_queryset = job_queryset.filter(experience_level=experience_level)
        if salary_range:
            lower, upper = form.SALARY_RANGES[salary_range]
            job_queryset = job_queryset.filter(salary_currency="SGD", salary_period="month").exclude(
                salary_min__isnull=True, salary_max__isnull=True,
            )
            if lower is not None:
                job_queryset = job_queryset.filter(Q(salary_max__gte=lower) | Q(salary_max__isnull=True))
            if upper is not None:
                job_queryset = job_queryset.filter(Q(salary_min__lt=upper) | Q(salary_min__isnull=True))
    else:
        # Invalid selections must not silently return every open job.
        job_queryset = job_queryset.none()

    saved_ids = set(SavedJob.objects.filter(candidate=request.user).values_list("job_id", flat=True))
    applied_ids = set(JobApplication.objects.filter(candidate=request.user).values_list("job_id", flat=True))
    has_pro = _current_profile(request).is_pro
    job_cards = []
    for job in job_queryset:
        match = get_or_update_match(request.user, job) if has_pro else None
        ml_prediction = predict_suitability(request.user, job) if has_pro else None
        job_cards.append({
            "job": job,
            "match": match,
            "ml_prediction": ml_prediction,
            "overall_score": calculate_overall_suitability(
                match.score if match else None,
                ml_prediction["score"] if ml_prediction else None,
            ),
            "is_saved": job.id in saved_ids,
            "has_applied": job.id in applied_ids,
        })
    sort = "match" if request.GET.get("sort") == "match" and request.user.profile.is_pro else "newest"
    if sort == "match":
        job_cards.sort(key=lambda card: (card["match"].score, card["job"].created_at, card["job"].pk), reverse=True)
    return render(request, "candidates/jobs.html", _context(request, form=form, job_cards=job_cards, sort=sort))


@candidate_required
def applications(request):
    application_list = JobApplication.objects.filter(candidate=request.user).select_related("job__company")
    has_pro = _current_profile(request).is_pro
    for application in application_list:
        ml_prediction = predict_suitability(request.user, application.job) if has_pro else None
        application.predicted_job_fit = ml_prediction["score"] if ml_prediction else None
    return render(request, "candidates/applications.html", _context(request, applications=application_list))


@candidate_required
def saved_jobs(request):
    if request.method == "POST":
        job = get_object_or_404(Job, pk=request.POST.get("job_id"))
        saved, created = SavedJob.objects.get_or_create(candidate=request.user, job=job)
        if not created:
            saved.delete()
        return redirect("candidate_saved_jobs")
    saved = SavedJob.objects.filter(candidate=request.user).select_related("job__company")
    applied_ids = set(JobApplication.objects.filter(candidate=request.user).values_list("job_id", flat=True))
    has_pro = _current_profile(request).is_pro
    job_cards = []
    for item in saved:
        match = get_or_update_match(request.user, item.job) if has_pro else None
        ml_prediction = predict_suitability(request.user, item.job) if has_pro else None
        job_cards.append({
            "job": item.job,
            "match": match,
            "ml_prediction": ml_prediction,
            "overall_score": calculate_overall_suitability(
                match.score if match else None,
                ml_prediction["score"] if ml_prediction else None,
            ),
            "is_saved": True,
            "has_applied": item.job_id in applied_ids,
        })
    return render(request, "candidates/jobs.html", _context(request, form=JobFilterForm(), job_cards=job_cards, saved_page=True))
