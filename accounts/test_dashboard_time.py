from datetime import datetime, timezone as dt_timezone, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from accounts.dashboard_helpers import dashboard_greeting
from applications.forms import InterviewForm


class SingaporeTimeTests(SimpleTestCase):
    def test_greeting_uses_singapore_hour_including_day_rollover(self):
        cases = [
            (datetime(2026, 11, 12, 0, tzinfo=dt_timezone.utc), 'Good Morning'),
            (datetime(2026, 11, 12, 4, tzinfo=dt_timezone.utc), 'Good Afternoon'),
            (datetime(2026, 11, 12, 10, tzinfo=dt_timezone.utc), 'Good Evening'),
            (datetime(2026, 11, 12, 23, tzinfo=dt_timezone.utc), 'Good Morning'),
        ]
        for now, expected in cases:
            with self.subTest(now=now), patch('accounts.dashboard_helpers.timezone.now', return_value=now):
                self.assertEqual(dashboard_greeting(), expected)

    @override_settings(TIME_ZONE='Asia/Singapore', USE_TZ=True)
    def test_interview_input_is_interpreted_as_singapore_time(self):
        with timezone.override('Asia/Singapore'):
            form = InterviewForm(data={'scheduled_start': '2026-11-14T20:00'})
            self.assertTrue(form.is_valid(), form.errors)
            start = form.cleaned_data['scheduled_start']
            self.assertEqual(start.utcoffset(), timedelta(hours=8))
            self.assertEqual(start.astimezone(dt_timezone.utc).hour, 12)
