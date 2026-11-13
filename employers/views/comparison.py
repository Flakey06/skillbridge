"""Read-only comparison of applications for the same recruiter-owned job."""
from django.shortcuts import get_object_or_404, render

from accounts.decorators import recruiter_required
from applications.models import JobApplication
from matching.ml_model import predict_suitability
from .common import _context


@recruiter_required
def compare_candidates(request, application_id):
    accessible = JobApplication.objects.filter(job__created_by=request.user).select_related(
        "candidate__profile", "job__company"
    )
    current = get_object_or_404(accessible, pk=application_id)
    choices = accessible.filter(job=current.job).exclude(pk=current.pk).order_by("candidate__username", "pk")
    selected_id = request.GET.get("compare", "")
    other = None
    if selected_id:
        other = get_object_or_404(choices, pk=selected_id if selected_id.isdecimal() else 0)
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    for application in (current, other):
        if application is not None and has_pro:
            application.ml_prediction = predict_suitability(application.candidate, application.job)
    return render(request, "employers/compare_candidates.html", _context(
        request, application=current, comparison_application=other, comparison_choices=choices,
    ))
