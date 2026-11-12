"""Password recovery and authenticated personal account settings."""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import (
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from ..choices import PHONE_COUNTRY_CODE_CHOICES
from ..settings_forms import AccountDetailsForm
from .common import _profile


password_reset = PasswordResetView.as_view(
    template_name="accounts/password_reset_form.html",
    email_template_name="accounts/password_reset_email.txt",
    subject_template_name="accounts/password_reset_subject.txt",
    success_url=reverse_lazy("password_reset_done"),
)
password_reset_done = PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html")
password_reset_confirm = PasswordResetConfirmView.as_view(
    template_name="accounts/password_reset_confirm.html",
    success_url=reverse_lazy("password_reset_complete"),
)
password_reset_complete = PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html")


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@login_required
@never_cache
def account_settings(request):
    profile = _profile(request)
    data = dict(profile.profile_data or {})
    code = data.get("phone_country_code") or "+65"
    phone = str(data.get("phone") or "").strip()
    for prefix, _ in sorted(PHONE_COUNTRY_CODE_CHOICES, key=lambda item: len(item[0]), reverse=True):
        if phone.startswith(prefix):
            code, phone = prefix, phone[len(prefix):].strip()
            break
    initial = {"name": profile.display_name, "email": request.user.email, "phone": phone, "phone_country_code": code}
    details_form = AccountDetailsForm(request.POST if request.method == "POST" else None, user=request.user, initial=initial)
    changing_password = request.method == "POST" and any(request.POST.get(key) for key in ("new_password1", "new_password2"))
    password_form = PasswordChangeForm(request.user, request.POST if request.method == "POST" else None)
    if not changing_password:
        for field in password_form.fields.values():
            field.required = False
    if request.method == "POST":
        details_valid = details_form.is_valid()
        password_valid = password_form.is_valid() if changing_password else True
        # Updating the recovery address requires proof of the current password.
        if details_valid and details_form.cleaned_data["email"].casefold() != request.user.email.casefold():
            if not request.user.check_password(request.POST.get("old_password", "")):
                password_form.add_error("old_password", "Enter your current password to change your email address.")
                password_valid = False
        if details_valid and password_valid:
            with transaction.atomic():
                values = details_form.cleaned_data
                request.user.email = values["email"]
                request.user.first_name, _, request.user.last_name = values["name"].partition(" ")
                request.user.save(update_fields=["email", "first_name", "last_name"])
                data.update({"name": values["name"], "email": values["email"], "phone_country_code": values["phone_country_code"],
                             "phone": f"{values['phone_country_code']} {values['phone']}" if values["phone"] else ""})
                profile.profile_data = data
                profile.save(update_fields=["profile_data"])
                if profile.role == "candidate":
                    from candidates.services import sync_candidate_profile
                    sync_candidate_profile(request.user, data)
                if changing_password:
                    password_form.save()
            if changing_password:
                update_session_auth_hash(request, request.user)
            request.session["onboarding_answers"] = data
            messages.success(request, "Your account settings have been updated.")
            return redirect("account_settings")
    return render(request, "accounts/settings.html", {
        "details_form": details_form, "password_form": password_form,
        "role": profile.role, "has_pro": profile.is_pro,
        "profile_url": "recruiter_company" if profile.role == "recruiter" else "candidate_profile",
    })
