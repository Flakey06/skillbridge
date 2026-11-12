"""Stripe checkout, subscription cancellation, and webhook handling."""

import json
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ..models import Payment, UserProfile
from ..payment_services import (
    PaymentProviderError,
    cancel_stripe_subscription,
    create_stripe_checkout,
    retrieve_stripe_checkout,
    set_stripe_entitlement,
    stripe_payment_for_subscription,
    verify_stripe_signature,
)
from ..notification_helpers import notify
from .common import _profile


@login_required
@require_POST
def cancel_pro(request):
    profile = _profile(request)
    if not profile.is_pro:
        messages.info(request, "Your account is already on the Free plan.")
        return redirect("plans")

    paid_payments = Payment.objects.filter(
        user=request.user,
        provider="stripe",
        status="paid",
    ).order_by("-created_at")
    payment = next(
        (
            item for item in paid_payments
            if (item.metadata or {}).get("subscription")
        ),
        None,
    )
    if not payment:
        if (profile.pro_trial_started_at or profile.trial_started_at) and profile.plan_expires_at:
            profile.plan = "free"
            profile.plan_expires_at = None
            profile.save(update_fields=["plan", "plan_expires_at"])
            messages.success(request, "Your Pro trial has ended. Your account is now on Free.")
        else:
            messages.error(request, "No active Stripe subscription was found for this account.")
        return redirect("plans")

    try:
        cancel_stripe_subscription(payment.metadata["subscription"])
    except PaymentProviderError as exc:
        messages.error(request, f"Stripe could not cancel the subscription: {exc}")
        return redirect("plans")

    payment.status = "cancelled"
    payment.save(update_fields=["status"])
    profile.plan = "free"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])
    notify(request.user, "Pro plan cancelled", "Your Pro plan was cancelled. Your account is now on SkillBridge Free.", "payment")
    return redirect("plans")


def _mark_payment_paid(payment, session_data):
    payment.status = "paid"
    payment.paid_at = timezone.now()
    payment.metadata = {
        "checkout_status": session_data.get("status", ""),
        "payment_status": session_data.get("payment_status", ""),
        "subscription": session_data.get("subscription", ""),
    }
    payment.save(update_fields=["status", "paid_at", "metadata"])
    profile = _profile_for_user(payment.user)
    profile.plan = "pro"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])


def _stripe_subscription_id(stripe_object):
    subscription = stripe_object.get("subscription") or (
        stripe_object.get("parent", {}).get("subscription_details", {}).get("subscription", "")
    )
    return subscription.get("id", "") if isinstance(subscription, dict) else subscription


def _profile_for_user(user):
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": "candidate"})
    return profile


@login_required
@require_POST
def start_pro_checkout(request):
    if _profile(request).is_pro:
        messages.info(request, "Your SkillBridge Pro plan is already active.")
        return redirect("plans")

    provider = request.POST.get("provider", "stripe")
    if provider != "stripe":
        messages.info(request, "Stripe test checkout is enabled first. PayPal sandbox and PayNow/DBS merchant flows can be added with their credentials.")
        return redirect("plans")
    if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        messages.error(request, "Stripe test mode is not configured yet. Add a Stripe sk_test_ key to your environment first.")
        return redirect("plans")

    amount = Decimal(settings.PRO_PLAN_AMOUNT_CENTS) / Decimal("100")
    payment = Payment.objects.create(
        user=request.user,
        provider="stripe",
        amount=amount,
        currency=settings.PRO_PLAN_CURRENCY.upper(),
    )
    success_url = request.build_absolute_uri(reverse("pro_payment_success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("plans"))
    try:
        session = create_stripe_checkout(
            user=request.user,
            payment_id=payment.id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except PaymentProviderError as exc:
        payment.status = "failed"
        payment.metadata = {"error": str(exc)}
        payment.save(update_fields=["status", "metadata"])
        messages.error(request, str(exc))
        return redirect("plans")

    payment.external_id = session.get("id", "")
    payment.checkout_url = session.get("url", "")
    payment.save(update_fields=["external_id", "checkout_url"])
    if not payment.checkout_url:
        payment.status = "failed"
        payment.metadata = {"error": "Stripe did not return a checkout URL."}
        payment.save(update_fields=["status", "metadata"])
        messages.error(request, "Stripe did not return a checkout URL.")
        return redirect("plans")
    return redirect(payment.checkout_url)


@login_required
def pro_payment_success(request):
    session_id = request.GET.get("session_id", "")
    payment = Payment.objects.filter(user=request.user, external_id=session_id, provider="stripe").first()
    if not payment:
        messages.error(request, "We could not match this checkout to your account.")
        return redirect("plans")
    try:
        session = retrieve_stripe_checkout(session_id)
    except PaymentProviderError as exc:
        messages.error(request, str(exc))
        return redirect("plans")
    if session.get("payment_status") == "paid" and session.get("status") == "complete":
        _mark_payment_paid(payment, session)
        notify(request.user, "Payment successful", "SkillBridge Pro is now active.", "payment")
    else:
        messages.info(request, "Checkout returned, but payment has not been confirmed yet.")
    return redirect("plans")


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not verify_stripe_signature(request.body, request.headers.get("Stripe-Signature", "")):
        return JsonResponse({"error": "Invalid Stripe signature."}, status=400)
    try:
        event = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    event_type = event.get("type", "")
    stripe_object = event.get("data", {}).get("object", {})
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        session = stripe_object
        payment_id = session.get("metadata", {}).get("payment_id")
        payment = Payment.objects.filter(pk=payment_id, provider="stripe").first()
        if payment and session.get("payment_status") == "paid":
            _mark_payment_paid(payment, session)
    elif event_type == "checkout.session.expired":
        payment_id = stripe_object.get("metadata", {}).get("payment_id")
        payment = Payment.objects.filter(pk=payment_id, provider="stripe").first()
        if payment:
            set_stripe_entitlement(payment, active=False, status="expired", stripe_status="expired")
    elif event_type in {"invoice.paid", "invoice.payment_failed"}:
        payment = stripe_payment_for_subscription(_stripe_subscription_id(stripe_object))
        if payment:
            paid = event_type == "invoice.paid"
            set_stripe_entitlement(
                payment,
                active=paid,
                status="paid" if paid else "past_due",
                stripe_status="active" if paid else "past_due",
            )
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = stripe_object.get("id", "")
        payment = stripe_payment_for_subscription(subscription_id)
        if payment:
            stripe_status = stripe_object.get("status", "cancelled")
            active = event_type != "customer.subscription.deleted" and stripe_status in {"active", "trialing"}
            deleted = event_type == "customer.subscription.deleted"
            local_status = "paid" if active else ("cancelled" if deleted or stripe_status == "canceled" else "past_due")
            set_stripe_entitlement(
                payment,
                active=active,
                status=local_status,
                stripe_status=stripe_status,
            )
    return JsonResponse({"received": True})
