"""Shared account lookup and safe navigation helpers."""

from django.utils.http import url_has_allowed_host_and_scheme
from ..models import UserProfile


def _role(request):
    return getattr(getattr(request.user, "profile", None), "role", "candidate")


def _profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": _role(request)})
    return profile


def _safe_next_url(request, value):
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ""
