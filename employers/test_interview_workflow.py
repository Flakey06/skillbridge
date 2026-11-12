from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from applications.forms import ApplicationStatusForm
from applications.models import JobApplication, Interview
from employers.models import Company
from jobs.models import Job


class InterviewSchedulingRulesTests(TestCase):
    def setUp(self):
        recruiter = User.objects.create_user(username='interview-rule-recruiter')
        UserProfile.objects.create(user=recruiter, role='recruiter')
        candidate = User.objects.create_user(username='interview-rule-candidate')
        company = Company.objects.create(name='Interview Company')
        job = Job.objects.create(title='Role', company=company, created_by=recruiter, employment_type='full_time')
        self.application = JobApplication.objects.create(candidate=candidate, job=job)
        self.client.force_login(recruiter)

    def test_schedule_button_requires_saved_shortlisted_status(self):
        url = reverse('recruiter_applicant_detail', args=[self.application.pk])
        for status in ['submitted', 'shortlisted', 'interview', 'offer', 'rejected', 'withdrawn']:
            self.application.status = status
            self.application.save(update_fields=['status'])
            response = self.client.get(url)
            if status == 'shortlisted':
                self.assertContains(response, f'?application={self.application.pk}')
            else:
                self.assertNotContains(response, 'applicant-schedule-interview')

    def test_interview_is_not_a_manual_status_choice(self):
        for status in ['submitted', 'interview']:
            self.application.status = status
            form = ApplicationStatusForm(instance=self.application)
            self.assertNotIn('interview', dict(form.fields['status'].choices))
            self.assertFalse(ApplicationStatusForm({'status': 'interview'}, instance=self.application).is_valid())

    def test_scheduling_shortlisted_application_sets_interview_automatically(self):
        self.application.status = 'shortlisted'
        self.application.save(update_fields=['status'])
        response = self.client.get(reverse('recruiter_calendar'), {'application': self.application.pk})
        self.assertEqual(response.context['selected_application'].pk, self.application.pk)
        response = self.client.post(reverse('recruiter_calendar'), {
            'application_id': self.application.pk, 'scheduled_start': '2026-12-01T14:00',
        })
        self.assertRedirects(response, reverse('recruiter_calendar'))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'interview')
        self.assertEqual(self.application.get_status_display(), 'Interview')
        self.assertEqual(Interview.objects.filter(application=self.application).count(), 1)

    def test_cannot_schedule_non_shortlisted_application_via_direct_post(self):
        response = self.client.post(reverse('recruiter_calendar'), {
            'application_id': self.application.pk, 'scheduled_start': '2026-12-01T14:00',
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Interview.objects.filter(application=self.application).exists())

    def test_status_save_returns_to_progress_section(self):
        url = reverse('recruiter_applicant_detail', args=[self.application.pk])
        response = self.client.post(url, {'status': 'shortlisted'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], url + '#update-progress')
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'shortlisted')
        response = self.client.get(url)
        self.assertContains(response, 'id="update-progress"')
