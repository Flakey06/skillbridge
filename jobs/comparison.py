from django.shortcuts import get_object_or_404, render

from accounts.decorators import candidate_required
from .models import Job


@candidate_required
def compare_jobs(request, job_id):
    visible = Job.objects.filter().select_related("company")
    current_job = get_object_or_404(visible, pk=job_id)
    choices = visible.filter(status="open").exclude(pk=job_id).order_by("title", "pk")
    selected_id = request.GET.get("compare", "")
    comparison_job = None
    if selected_id:
        # Resolve against the same public choices shown in the selector.
        comparison_job = get_object_or_404(choices, pk=selected_id if selected_id.isdecimal() else 0)
    return render(request, "jobs/compare.html", {
        "job": current_job,
        "comparison_job": comparison_job,
        "comparison_choices": choices,
    })
