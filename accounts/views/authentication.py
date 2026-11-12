"""Registration, login, logout, and signup company lookup."""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET
from employers.services import lookup_company
from ..forms import SignupForm
from ..models import UserProfile
from .common import _profile, _safe_next_url
from .onboarding_helpers import CANDIDATE_STEPS, RECRUITER_STEPS, _next_step


def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
    requested_next = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=identifier, password=password)
        if user is None and "@" in identifier:
            email_user = User.objects.filter(email__iexact=identifier).first()
            if email_user:
                user = authenticate(request, username=email_user.username, password=password)
        if user is not None:
            login(request, user)
            profile = _profile(request)
            steps = RECRUITER_STEPS if profile.role == "recruiter" else CANDIDATE_STEPS
            request.session["onboarding_answers"] = profile.profile_data or {}
            request.session["onboarding_step"] = _next_step(profile, steps)
            # Onboarding is required immediately after signup, but logging in
            # to an existing account should always return to its workspace.
            # Users can still continue or edit the questionnaire from Profile.
            request.session["onboarding_complete"] = True
            return redirect(requested_next or "home")
        form.add_error(None, "Invalid username/email or password.")
    return render(request, "accounts/login.html", {"form": form})


def signup_view(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserProfile.objects.create(user=user, role=form.cleaned_data["role"])
        if form.cleaned_data["role"] == "recruiter" and form.cleaned_data.get("company_name"):
            from employers.models import Company, RecruiterProfile

            company = Company.objects.create(
                name=form.cleaned_data["company_name"],
                website=form.cleaned_data.get("company_website", ""),
                logo_url=form.cleaned_data.get("company_logo_url", ""),
            )
            RecruiterProfile.objects.create(user=user, company=company)
        login(request, user)
        request.session["onboarding_step"] = 0
        request.session["onboarding_answers"] = {}
        request.session["onboarding_complete"] = False
        request.session["sandy_intro_seen"] = False
        requested_next = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
        if requested_next:
            request.session["post_onboarding_next"] = requested_next
        return redirect("onboarding")
    return render(request, "accounts/signup.html", {"form": form})


@require_GET
def signup_company_lookup(request):
    query = request.GET.get("q", "").strip()
    return JsonResponse({"query": query, "result": lookup_company(query) if query else None})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")
