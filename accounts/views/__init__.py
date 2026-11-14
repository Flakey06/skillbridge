"""Stable view imports; implementations are grouped by feature."""

from .common import _role, _profile, _safe_next_url
from .onboarding_helpers import (
    CANDIDATE_STEPS,
    RECRUITER_STEPS,
    _step_value,
    _profile_is_complete,
    _next_step,
    _finish_onboarding,
    _resume_form_initial,
    _save_resume_form,
)
from .authentication import login_view, signup_view, logout_view
from .onboarding import (
    onboarding,
    scan_resume_upload,
    delete_onboarding_resume,
    autosave_resume_draft,
)
from .plans import plans, start_pro_trial, pro_checkout_confirm, cancel_pro_confirm
from .payments import (
    cancel_pro,
    _mark_payment_paid,
    _stripe_subscription_id,
    _profile_for_user,
    start_pro_checkout,
    pro_payment_success,
    stripe_webhook,
)
from .notifications import inbox
from .dashboard import home
from .feedback import feedback

__all__ = [
    'CANDIDATE_STEPS',
    'RECRUITER_STEPS',
    'home',
    'inbox',
    'feedback',
    'login_view',
    'signup_view',
    'onboarding',
    'scan_resume_upload',
    'delete_onboarding_resume',
    'autosave_resume_draft',
    'logout_view',
    'plans',
    'start_pro_trial',
    'pro_checkout_confirm',
    'cancel_pro_confirm',
    'cancel_pro',
    'start_pro_checkout',
    'pro_payment_success',
    'stripe_webhook',
]
