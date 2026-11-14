from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import UserProfile, Notification
from applications.models import Interview, InterviewReminder, JobApplication
from employers.models import Company
from jobs.models import Job


class InterviewReminderTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.recruiter = User.objects.create_user(username='reminder-recruiter')
        UserProfile.objects.create(user=self.recruiter, role='recruiter')
        self.candidate = User.objects.create_user(username='reminder-candidate')
        UserProfile.objects.create(user=self.candidate, role='candidate')
        company = Company.objects.create(name='Reminder Company')
        job = Job.objects.create(title='Reminder Engineer', company=company,
            created_by=self.recruiter, employment_type='full_time')
        self.application = JobApplication.objects.create(candidate=self.candidate, job=job, status='interview')
        self.interview = Interview.objects.create(application=self.application, created_by=self.recruiter,
            scheduled_start=self.now + timedelta(minutes=30), candidate_response='accepted')

    def page(self, user):
        self.client.force_login(user)
        url = 'candidate_calendar' if user == self.candidate else 'recruiter_calendar'
        with patch('accounts.interview_reminders.timezone.now', return_value=self.now):
            return self.client.get(reverse(url))

    def test_both_participants_receive_one_toast_each_without_inbox_messages(self):
        for user in (self.candidate, self.recruiter):
            response = self.page(user)
            self.assertContains(response, 'Interview reminder: Reminder Engineer starts in 30 minutes')
            self.assertContains(response, 'SGT')
            self.assertNotContains(self.page(user), 'Interview reminder:')
        self.assertEqual(InterviewReminder.objects.count(), 2)
        self.assertFalse(Notification.objects.filter(title__icontains='reminder').exists())

    def test_outside_window_past_and_unrelated_user_do_not_receive_reminders(self):
        self.interview.scheduled_start = self.now + timedelta(minutes=31)
        self.interview.save()
        self.assertNotContains(self.page(self.candidate), 'Interview reminder:')
        self.interview.scheduled_start = self.now - timedelta(minutes=1)
        self.interview.save()
        self.assertNotContains(self.page(self.candidate), 'Interview reminder:')
        self.interview.scheduled_start = self.now + timedelta(minutes=15)
        self.interview.save()
        other = User.objects.create_user(username='unrelated-reminder-user')
        UserProfile.objects.create(user=other, role='recruiter')
        self.assertNotContains(self.page(other), 'Interview reminder:')
        self.assertFalse(InterviewReminder.objects.exists())

    def test_rescheduled_interview_can_generate_a_new_reminder(self):
        self.page(self.candidate)
        self.interview.scheduled_start = self.now + timedelta(minutes=20)
        self.interview.save()
        self.assertContains(self.page(self.candidate), 'starts in 20 minutes')
        self.assertEqual(InterviewReminder.objects.count(), 2)

    def test_withdrawn_application_does_not_receive_reminder(self):
        self.application.status = 'withdrawn'
        self.application.save()
        self.assertNotContains(self.page(self.candidate), 'Interview reminder:')
        self.assertFalse(InterviewReminder.objects.exists())
