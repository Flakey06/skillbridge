from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from applications.models import JobApplication
from jobs.models import Job
from .models import Company, RecruiterProfile


class ListingApplicantCountTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(username='count-recruiter')
        UserProfile.objects.create(user=self.recruiter, role='recruiter')
        company = Company.objects.create(name='Count Company')
        RecruiterProfile.objects.create(user=self.recruiter, company=company)
        self.job = Job.objects.create(title='First Role', company=company, created_by=self.recruiter, employment_type='full_time')
        self.other_job = Job.objects.create(title='Second Role', company=company, created_by=self.recruiter, employment_type='full_time')
        self.candidate = User.objects.create_user(username='count-candidate')
        self.client.force_login(self.recruiter)

    def test_count_updates_and_links_to_exact_job(self):
        url = reverse('recruiter_listings')
        self.assertEqual(next(j for j in self.client.get(url).context['jobs'] if j.pk == self.job.pk).applicant_count, 0)
        application = JobApplication.objects.create(candidate=self.candidate, job=self.job)
        response = self.client.get(url)
        self.assertEqual(next(j for j in response.context['jobs'] if j.pk == self.job.pk).applicant_count, 1)
        target = reverse('recruiter_applicants') + f'?job={self.job.pk}'
        self.assertContains(response, f'href="{target}"')
        self.assertContains(response, 'Tap To View')
        JobApplication.objects.create(candidate=self.candidate, job=self.other_job)
        filtered = self.client.get(target)
        self.assertEqual([a.pk for a in filtered.context['applications']], [application.pk])
        application.delete()
        self.assertEqual(next(j for j in self.client.get(url).context['jobs'] if j.pk == self.job.pk).applicant_count, 0)

    def test_listing_counts_exclude_other_recruiters_jobs(self):
        outsider = User.objects.create_user(username='other-count-recruiter')
        Job.objects.create(title='Private Role', company=self.job.company, created_by=outsider, employment_type='full_time')
        response = self.client.get(reverse('recruiter_listings'))
        self.assertEqual({j.pk for j in response.context['jobs']}, {self.job.pk, self.other_job.pk})

    def test_save_keeps_selected_submitted_status(self):
        application = JobApplication.objects.create(candidate=self.candidate, job=self.job)
        response = self.client.post(reverse('recruiter_applicants'), {
            'application_id': application.pk, 'status': 'submitted',
        })
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.status, 'submitted')

    def test_save_updates_to_selected_status(self):
        application = JobApplication.objects.create(candidate=self.candidate, job=self.job)
        self.client.post(reverse('recruiter_applicants'), {
            'application_id': application.pk, 'status': 'rejected',
        })
        application.refresh_from_db()
        self.assertEqual(application.status, 'rejected')
