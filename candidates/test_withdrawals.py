from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile, Notification
from applications.forms import ApplicationStatusForm
from applications.models import JobApplication, Interview
from employers.models import Company
from jobs.models import Job


class CandidateWithdrawalTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(username='withdraw-candidate')
        UserProfile.objects.create(user=self.candidate, role='candidate')
        self.recruiter = User.objects.create_user(username='withdraw-recruiter')
        UserProfile.objects.create(user=self.recruiter, role='recruiter')
        company = Company.objects.create(name='Withdraw Company')
        self.job = Job.objects.create(title='Withdraw Role', company=company, created_by=self.recruiter, employment_type='full_time')
        self.application = JobApplication.objects.create(candidate=self.candidate, job=self.job, status='shortlisted', cover_note='Keep this note')
        self.url = reverse('candidate_withdraw_application', args=[self.application.pk])
        self.client.force_login(self.candidate)

    def test_withdrawal_preserves_history_and_is_idempotent(self):
        response = self.client.post(self.url)
        self.assertEqual(response['Location'], reverse('candidate_applications') + f'#application-{self.application.pk}')
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'withdrawn')
        self.assertEqual(self.application.cover_note, 'Keep this note')
        self.client.post(self.url)
        self.assertEqual(Notification.objects.filter(recipient=self.recruiter, title='Application withdrawn').count(), 1)
        response = self.client.get(reverse('candidate_applications'))
        self.assertContains(response, '>Withdrawn</button>')

    def test_job_page_has_separate_controls_and_returns_to_job(self):
        response = self.client.get(reverse('job_detail', args=[self.job.pk]))
        self.assertContains(response, 'Already Applied')
        self.assertContains(response, f'action="{self.url}"')
        response = self.client.post(self.url, {'return_to': 'job'})
        self.assertEqual(response['Location'], reverse('job_detail', args=[self.job.pk]) + '#job-application-title')

    def test_other_candidate_and_recruiter_cannot_withdraw(self):
        other = User.objects.create_user(username='other-withdraw-candidate')
        UserProfile.objects.create(user=other, role='candidate')
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.client.force_login(self.recruiter)
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'shortlisted')

    def test_withdrawal_requires_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'shortlisted')

    def test_recruiter_cannot_select_withdrawn_or_restore_withdrawn_application(self):
        self.assertNotIn('withdrawn', dict(ApplicationStatusForm(instance=self.application).fields['status'].choices))
        self.client.post(self.url)
        self.client.force_login(self.recruiter)
        for url in [reverse('recruiter_applicants'), reverse('recruiter_applicant_detail', args=[self.application.pk])]:
            self.client.post(url, {'application_id': self.application.pk, 'status': 'shortlisted'})
            self.application.refresh_from_db()
            self.assertEqual(self.application.status, 'withdrawn')
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertNotContains(response, '<option value="withdrawn"', html=False)
        response = self.client.get(reverse('recruiter_applicants'), {'status': 'withdrawn'})
        self.assertEqual(list(response.context['applications']), [])

    def test_withdrawn_interviews_not_in_candidate_calendar_or_export(self):
        interview = Interview.objects.create(application=self.application, created_by=self.recruiter, scheduled_start=timezone.now() + timedelta(days=2))
        self.client.post(self.url)
        response = self.client.get(reverse('candidate_calendar'))
        self.assertEqual(list(response.context['interviews']), [])
        response = self.client.get(reverse('candidate_calendar'), {'download': 'ics'})
        self.assertNotIn(b'BEGIN:VEVENT', response.content)
        self.assertTrue(Interview.objects.filter(pk=interview.pk).exists())

    def test_rejected_and_offer_applications_cannot_be_withdrawn(self):
        for status in ['rejected', 'offer']:
            self.application.status = status
            self.application.save(update_fields=['status'])
            for url in [reverse('candidate_applications'), reverse('job_detail', args=[self.job.pk])]:
                response = self.client.get(url)
                self.assertNotContains(response, f'action="{self.url}"')
            self.assertEqual(self.client.post(self.url).status_code, 403)
            self.application.refresh_from_db()
            self.assertEqual(self.application.status, status)

    def test_final_outcome_replaces_applied_actions_on_job_page(self):
        for status, label in [('rejected', 'Rejected'), ('offer', 'Offered')]:
            self.application.status = status
            self.application.save(update_fields=['status'])
            response = self.client.get(reverse('job_detail', args=[self.job.pk]))
            self.assertContains(response, 'candidate-application-outcome')
            self.assertContains(response, f'role="status">{label}</div>')
            self.assertNotContains(response, 'candidate-applied-actions')
            self.assertNotContains(response, '>Already Applied</button>')
