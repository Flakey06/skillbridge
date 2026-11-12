"""Shared time-aware dashboard text."""

from zoneinfo import ZoneInfo

from django.utils import timezone


def dashboard_greeting():
    hour = timezone.localtime(timezone.now(), ZoneInfo("Asia/Singapore")).hour
    if 5 <= hour < 12:
        return "Good Morning"
    if 12 <= hour < 18:
        return "Good Afternoon"
    return "Good Evening"
