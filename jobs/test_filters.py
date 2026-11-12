from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company
from .models import Job


class JobDiscoveryFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="filter-candidate")
        UserProfile.objects.create(user=self.user, role="candidate")
        self.recruiter = User.objects.create_user(username="filter-recruiter")
        self.company = Company.objects.create(name="Filter Company")
        self.client.force_login(self.user)
        self.url = reverse('candidate_jobs')
        matcher = patch('candidates.views.jobs.get_or_update_match', return_value=SimpleNamespace(score=50))
        matcher.start()
        self.addCleanup(matcher.stop)

    def job(self, title, **kwargs):
        return Job.objects.create(title=title, company=self.company, created_by=self.recruiter,
                                  employment_type='full_time', **kwargs)

    def results(self, **filters):
        response = self.client.get(self.url, filters)
        self.assertEqual(response.status_code, 200)
        return response, [card['job'].pk for card in response.context['job_cards']]

    def test_skills_match_whole_names_case_insensitively_and_require_all(self):
        match = self.job('Complete', required_skills=' Python,\nSQL , C++')
        self.job('NoSQL', required_skills='Python, NoSQL')
        self.job('Only SQL', required_skills='SQL')
        self.job('Preferred only', preferred_skills='Python, SQL')
        self.assertEqual(self.results(required_skills='python, sql')[1], [match.pk])
        self.assertEqual(self.results(required_skills='C++')[1], [match.pk])

    def test_salary_overlap_excludes_unknown_other_currencies_and_periods(self):
        overlap = self.job('Overlap', salary_min=3500, salary_max=4500)
        self.job('Below', salary_min=2000, salary_max=3999)
        self.job('Above', salary_min=6000, salary_max=7000)
        self.job('Unknown')
        self.job('USD', salary_min=4000, salary_max=5000, salary_currency='USD')
        self.job('Annual', salary_min=4000, salary_max=5000, salary_period='year')
        self.assertEqual(self.results(salary_range='4000_5999')[1], [overlap.pk])

    def test_salary_boundaries_and_open_ended_listings(self):
        boundary = self.job('Boundary', salary_min=2000, salary_max=2000)
        capped = self.job('Up to', salary_max=1999)
        minimum = self.job('From', salary_min=8000)
        self.assertEqual(self.results(salary_range='under_2000')[1], [capped.pk])
        self.assertEqual(self.results(salary_range='2000_3999')[1], [boundary.pk])
        self.assertEqual(self.results(salary_range='8000_plus')[1], [minimum.pk])

    def test_filters_combine_and_values_are_preserved(self):
        match = self.job('Backend Engineer', location='Singapore', experience_level='junior',
                         required_skills='Python, SQL', salary_min=3000, salary_max=5000)
        self.job('Senior Backend', location='Singapore', experience_level='senior',
                 required_skills='Python', salary_min=3000, salary_max=5000)
        response, ids = self.results(q='Backend', location='Singapore', employment_type='full_time',
                                    experience_level='junior', required_skills='Python', salary_range='4000_5999')
        self.assertEqual(ids, [match.pk])
        self.assertEqual(response.context['form']['salary_range'].value(), '4000_5999')
        self.assertEqual(response.context['form']['required_skills'].value(), 'Python')

    def test_invalid_choices_show_errors_without_returning_all_jobs(self):
        self.job('Open')
        for filters in [dict(salary_range='invalid'), dict(experience_level='invalid')]:
            response, ids = self.results(**filters)
            self.assertEqual(ids, [])
            self.assertTrue(response.context['form'].errors)

    def test_no_filters_keeps_open_jobs_with_undisclosed_salary(self):
        open_job = self.job('Open')
        self.job('Closed', status='closed')
        self.assertEqual(self.results()[1], [open_job.pk])

    def test_match_sort_remains_pro_only_with_filters(self):
        job = self.job('Python', required_skills='Python')
        response, ids = self.results(sort='match', required_skills='Python')
        self.assertEqual(ids, [job.pk])
        self.assertEqual(response.context['sort'], 'newest')
        profile = self.user.profile
        profile.plan = "pro"
        profile.save(update_fields=['plan'])
        response, _ = self.results(sort='match', required_skills='Python')
        self.assertEqual(response.context['sort'], 'match')
