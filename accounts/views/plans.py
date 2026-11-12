"""Plan display, local Pro trial, and cancellation confirmation."""

from datetime import timedelta
from django.db import transaction
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..models import Payment, UserProfile
from ..notification_helpers import notify
from .common import _profile


@login_required
def plans(request):
    profile = _profile(request)
    return render(
        request,
        "accounts/plans.html",
        {
            "role": profile.role,
            "profile": profile,
            "has_pro": profile.is_pro,
            "trial_available": not (profile.pro_trial_started_at or profile.trial_started_at) and not profile.is_pro,
            "payments": Payment.objects.filter(user=request.user)[:5],
            "stripe_enabled": settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
            "pro_plan_price": f"{settings.PRO_PLAN_CURRENCY.upper()} {settings.PRO_PLAN_AMOUNT_CENTS / 100:.2f}",
        },
    )


@login_required
@require_POST
def start_pro_trial(request):
    now = timezone.now()
    with transaction.atomic():
        profile = _profile(request)
        if profile.is_pro:
            messages.info(request, "Your Pro access is already active.")
        else:
            granted = UserProfile.objects.filter(
                pk=profile.pk, pro_trial_started_at__isnull=True,
            ).update(
                plan="pro",
                plan_expires_at=now + timedelta(days=7),
                pro_trial_started_at=now,
                trial_started_at=now,
            )
            if granted:
                notify(request.user, "Pro trial started", "Your seven-day Pro trial is active. It ends automatically; no payment details are needed.", "account")
                messages.success(request, "Your seven-day Pro trial is now active.")
            else:
                messages.info(request, "You have already used your seven-day Pro trial.")
    return redirect("plans")


@login_required
def pro_checkout_confirm(request):
    profile = _profile(request)
    if profile.is_pro:
        messages.info(request, "Your SkillBridge Pro plan is already active.")
        return redirect("plans")
    return render(
        request,
        "accounts/checkout_confirm.html",
        {
            "profile": profile,
            "stripe_enabled": settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
            "pro_plan_price": f"{settings.PRO_PLAN_CURRENCY.upper()} {settings.PRO_PLAN_AMOUNT_CENTS / 100:.2f}",
        },
    )


@login_required
def cancel_pro_confirm(request):
    profile = _profile(request)
    if not profile.is_pro:
        messages.info(request, "Your account is already on the Free plan.")
        return redirect("plans")
    return render(request, "accounts/cancel_pro_confirm.html", {"profile": profile})
