"""Job listing creation, editing, and deletion."""

from django.contrib import messages
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
    jobs = Job.objects.filter(created_by=request.user).select_related("company")
    return render(request, "employers/listings.html", _context(request, jobs=jobs, form=form, company=recruiter.company))


@recruiter_required
def create_listing(request):
    recruiter = _recruiter(request)
    form = JobForm(request.POST or None)
    response = _publish_listing(request, recruiter, form)
    if response:
        return response
    return render(request, "employers/create_listing.html", _context(request, form=form, company=recruiter.company))


@recruiter_required
def edit_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job listing updated.")
        return redirect("recruiter_listings")
    recruiter = _recruiter(request)
    return render(
        request,
        "employers/create_listing.html",
        _context(request, form=form, company=recruiter.company, editing=True, job=job),
    )


@recruiter_required
def delete_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    if request.method == "POST":
        title = job.title
        job.delete()
        messages.success(request, f'Job listing "{title}" was deleted.')
        return redirect("recruiter_listings")
    return render(request, "employers/delete_listing.html", _context(request, job=job))
