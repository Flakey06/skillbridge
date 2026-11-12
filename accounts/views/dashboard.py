"""Role-aware home routing and onboarding entry."""

from django.shortcuts import redirect, render
from .common import _role, _profile
from .onboarding_helpers import CANDIDATE_STEPS, RECRUITER_STEPS, _profile_is_complete, _next_step


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    role = _role(request)
    profile = _profile(request)
    steps = RECRUITER_STEPS if role == "recruiter" else CANDIDATE_STEPS
    if not request.session.get("onboarding_complete") and not _profile_is_complete(profile, steps):
        request.session["onboarding_step"] = _next_step(profile, steps)
        return redirect("onboarding")
    if role == "recruiter":
        from employers.views import dashboard

        return dashboard(request)

    from candidates.views import dashboard_context

    return render(request, "candidates/dashboard.html", dashboard_context(request))
