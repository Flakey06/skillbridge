from datetime import date

from django.test import SimpleTestCase

from .calendar import build_month_calendar


class CalendarBuilderTests(SimpleTestCase):
    def test_month_navigation_handles_december(self):
        calendar_data = build_month_calendar([], month_value="2026-12", selected_value="2026-12-15")

        self.assertEqual(calendar_data["previous_month"], date(2026, 11, 1))
        self.assertEqual(calendar_data["next_month"], date(2027, 1, 1))
        self.assertEqual(calendar_data["selected_date"], date(2026, 12, 15))


from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import UserProfile
from applications.models import Interview, JobApplication
from employers.models import Company
from jobs.models import Job


class CalendarDownloadTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(username="calendar-candidate")
        self.recruiter = User.objects.create_user(username="calendar-recruiter")
        UserProfile.objects.create(user=self.candidate, role="candidate")
        UserProfile.objects.create(user=self.recruiter, role="recruiter")
        self.company = Company.objects.create(name="Test, Company")
        job = Job.objects.create(title="Engineer", company=self.company, created_by=self.recruiter)
        application = JobApplication.objects.create(candidate=self.candidate, job=job, status="interview")
        self.interview = Interview.objects.create(
            application=application, created_by=self.recruiter,
            scheduled_start=timezone.now() + timedelta(days=2),
            meeting_url="https://example.com/meeting", notes="Recruiter private notes",
            candidate_notes="Candidate private notes",
        )

    def test_download_for_both_roles_uses_attachment_and_confirmed_times(self):
        for user, route in [(self.candidate, 'candidate_calendar'), (self.recruiter, 'recruiter_calendar')]:
            self.client.force_login(user)
            response = self.client.get(reverse(route), {'download': 'ics'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
            content = response.content.decode().replace('\r\n ', '')
            self.assertIn('BEGIN:VCALENDAR\r\n', content)
            self.assertIn(f'UID:skillbridge-interview-{self.interview.pk}@skillbridge.local', content)
            self.assertIn('https://example.com/meeting', content)
            self.assertNotIn('private notes', content)
            self.assertNotIn('DTEND:', content)

    def test_other_users_interviews_are_excluded(self):
        outsider = User.objects.create_user(username="calendar-outsider")
        UserProfile.objects.create(user=outsider, role="candidate")
        self.client.force_login(outsider)
        response = self.client.get(reverse('candidate_calendar'), {'download': 'ics'})
        self.assertNotIn(b'BEGIN:VEVENT', response.content)

    def test_reschedule_shows_toast_once_on_next_visit(self):
        self.client.force_login(self.candidate)
        url = reverse('candidate_calendar')
        self.client.get(url, {'download': 'ics'})
        self.interview.scheduled_start += timedelta(days=1)
        self.interview.save(update_fields=['scheduled_start'])
        response = self.client.get(url)
        self.assertContains(response, 'Your interview calendar has changed.')
        self.assertNotContains(self.client.get(url), 'Your interview calendar has changed.')

    def test_private_notes_do_not_trigger_download_reminder(self):
        self.client.force_login(self.candidate)
        url = reverse('candidate_calendar')
        self.client.get(url)
        self.interview.notes = 'Updated notes'
        self.interview.save(update_fields=['notes'])
        self.assertNotContains(self.client.get(url), 'Your interview calendar has changed.')

    def test_unicode_and_newline_escape_and_line_folding(self):
        from accounts.calendar import _calendar_text, _fold_calendar_line
        self.assertEqual(_calendar_text('A, B; C\nD\\E'), r'A\, B\; C\nD\\E')
        value = 'SUMMARY:' + '面试' * 50
        folded = _fold_calendar_line(value)
        self.assertEqual(folded.replace('\r\n ', ''), value)
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in folded.split('\r\n')))
