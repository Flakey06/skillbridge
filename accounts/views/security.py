"""Password recovery and authenticated personal account settings."""

from django.conf import settings
from django.contrib import messages
from django import forms
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import (
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from ..choices import PHONE_COUNTRY_CODE_CHOICES
from ..forms import SecurityQuestionSettingsForm
from ..models import SecurityQuestionAnswer
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


class SecurityRecoveryLookupForm(forms.Form):
    identifier = forms.CharField(label="Username", max_length=254)


class SecurityRecoveryAnswersForm(forms.Form):
    def __init__(self, *args, records, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = list(records)
        for record in self.records:
            self.fields[f"answer_{record.position}"] = forms.CharField(
                label=record.get_question_display(),
                max_length=200,
                widget=forms.PasswordInput,
            )

    def answers_match(self):
        return all(
            record.answer_matches(self.cleaned_data.get(f"answer_{record.position}", ""))
            for record in self.records
        )


@sensitive_post_parameters()
@never_cache
def security_question_recovery(request):
    now = timezone.now().timestamp()
    locked_until = float(request.session.get("security_recovery_locked_until", 0) or 0)
    if locked_until > now:
        return render(request, "accounts/security_recovery.html", {
            "locked": True,
            "retry_minutes": max(1, round((locked_until - now) / 60)),
        })

    user = None
    user_id = request.session.get("security_recovery_user_id")
    if user_id:
        user = User.objects.filter(pk=user_id, is_active=True).first()
    if not user:
        lookup_form = SecurityRecoveryLookupForm(request.POST or None)
        if request.method == "POST" and lookup_form.is_valid():
            identifier = lookup_form.cleaned_data["identifier"].strip()
            user = User.objects.filter(
                Q(username__iexact=identifier) | Q(email__iexact=identifier), is_active=True
            ).first()
            if user and user.security_question_answers.count() == 3:
                request.session["security_recovery_user_id"] = user.pk
                request.session["security_recovery_attempts"] = 0
                return redirect("security_question_recovery")
            lookup_form.add_error(None, "Security-question recovery is unavailable for this account. Use the email reset option.")
        return render(request, "accounts/security_recovery.html", {"lookup_form": lookup_form})

    records = user.security_question_answers.all()
    if records.count() != 3:
        request.session.pop("security_recovery_user_id", None)
        return redirect("security_question_recovery")
    answer_form = SecurityRecoveryAnswersForm(
        request.POST or None,
        records=records,
    )
    if request.method == "POST" and answer_form.is_valid():
        if answer_form.answers_match():
            request.session["security_recovery_verified_at"] = now
            request.session["security_recovery_attempts"] = 0
            return redirect("security_question_password_hint")
        attempts = int(request.session.get("security_recovery_attempts", 0)) + 1
        request.session["security_recovery_attempts"] = attempts
        if attempts >= 5:
            request.session.pop("security_recovery_user_id", None)
            request.session["security_recovery_locked_until"] = now + 900
            return redirect("security_question_recovery")
        answer_form.add_error(None, f"The answers did not match. {5 - attempts} attempt(s) remain.")
    return render(request, "accounts/security_recovery.html", {"answer_form": answer_form})


@never_cache
def security_question_password_hint(request):
    user_id = request.session.get("security_recovery_user_id")
    verified_at = float(request.session.get("security_recovery_verified_at", 0) or 0)
    if not user_id or timezone.now().timestamp() - verified_at > 600:
        return redirect("security_question_recovery")
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if not user:
        return redirect("security_question_recovery")
    profile = getattr(user, "profile", None)
    return render(request, "accounts/security_question_hint.html", {
        "password_hint": profile.password_hint if profile else "",
    })


@sensitive_post_parameters()
@login_required
@never_cache
def security_question_settings(request):
    form = SecurityQuestionSettingsForm(
        request.POST or None,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, "Your security questions and password hint were updated.")
        return redirect("security_question_settings")
    return render(request, "accounts/security_question_settings.html", {
        "form": form,
        "has_security_questions": request.user.security_question_answers.count() == 3,
    })


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
        "stripe_enabled": settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
        "billing_demo": bool(profile.is_pro and profile.plan_expires_at and (profile.pro_trial_started_at or profile.trial_started_at)),
        "role": profile.role, "has_pro": profile.is_pro, "profile": profile,
        "profile_url": "recruiter_company" if profile.role == "recruiter" else "candidate_profile",
    })
