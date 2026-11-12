"""Job listing creation, editing, and deletion."""

from jobs.reference_catalog import suggest_skills_for_title
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from accounts.decorators import recruiter_required
from jobs.forms import JobForm
from jobs.models import Job
from .common import _recruiter, _context


def _publish_listing(request, recruiter, form):
    if request.method == "POST" and form.is_valid():
        if recruiter.company is None:
            messages.error(request, "Complete your company profile before creating a listing.")
        else:
            job = form.save(commit=False)
            job.company = recruiter.company
            job.created_by = request.user
            job.save()
            messages.success(request, "Job listing created.")
            return redirect("recruiter_listings")
    return None


@recruiter_required
def listings(request):
    recruiter = _recruiter(request)
    form = JobForm(request.POST or None)
    response = _publish_listing(request, recruiter, form)
    if response:
        return response
    jobs = Job.objects.filter(created_by=request.user).select_related("company").annotate(applicant_count=Count("applications"))
    return render(request, "employers/listings.html", _context(request, jobs=jobs, form=form, company=recruiter.company))


@recruiter_required
def create_listing(request):
    recruiter = _recruiter(request)
    action = request.POST.get("action", "") if request.method == "POST" else ""
    reference_kind, _, reference_index = action.partition(":")
    reference_action = reference_kind in {"suggest_reference", "use_reference_required", "use_reference_preferred"}
    form_data = request.POST or None
    suggestions = []

    if reference_action:
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.is_pro:
            messages.error(request, "Pro access is required for reference suggestions.")
        else:
            title = request.POST.get("title", "").strip()
            if title:
                try:
                    suggestions = suggest_skills_for_title(title)
                except (FileNotFoundError, OSError, ValueError) as error:
                    messages.error(request, f"Reference catalogue unavailable: {error}")
        if suggestions and reference_kind in {"use_reference_required", "use_reference_preferred"}:
            try:
                suggestion = suggestions[int(reference_index)]
            except (IndexError, TypeError, ValueError):
                messages.error(request, "That reference match is no longer available.")
            else:
                form_data = request.POST.copy()
                field_name = "required_skills" if reference_kind.endswith("required") else "preferred_skills"
                form_data[field_name] = ", ".join(suggestion["skills"])

    form = JobForm(form_data)
    response = None if reference_action else _publish_listing(request, recruiter, form)
    if response:
        return response
    return render(
        request,
        "employers/create_listing.html",
        _context(request, form=form, company=recruiter.company, suggestions=suggestions),
    )


@recruiter_required
def edit_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job listing updated.")
        return redirect("recruiter_job_detail", job_id=job.id)
    return render(request, "employers/edit_listing.html", _context(request, form=form, job=job))


@recruiter_required
def delete_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    if request.method == "POST":
        title = job.title
        job.delete()
        messages.success(request, f'Job listing "{title}" was deleted.')
        return redirect("recruiter_listings")
    return render(request, "employers/delete_listing.html", _context(request, job=job))


@recruiter_required
def job_detail(request, job_id):
    job = get_object_or_404(
        Job.objects.select_related("company"),
        pk=job_id,
        created_by=request.user,
    )
    return render(request, "employers/job_detail.html", _context(request, job=job))
