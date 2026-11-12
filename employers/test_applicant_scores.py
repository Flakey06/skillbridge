from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from applications.models import JobApplication
from jobs.models import Job
from .models import Company


class ApplicantScoreDisplayTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(username='score-recruiter')
        self.profile = UserProfile.objects.create(user=self.recruiter, role='recruiter', plan='pro')
        candidate = User.objects.create_user(username='score-candidate')
        company = Company.objects.create(name='Score Company')
        job = Job.objects.create(title='Score Role', company=company, created_by=self.recruiter, employment_type='full_time')
        self.application = JobApplication.objects.create(candidate=candidate, job=job, match_score=32)
        self.client.force_login(self.recruiter)

    @patch('employers.views.applicants.predict_suitability', return_value={'score': 78})
    def test_separate_skill_snapshot_and_ml_prediction(self, predictor):
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, 'Skill Compatibility')
        self.assertContains(response, 'Predicted Job Fit')
        self.assertContains(response, '<strong>32%</strong>', html=True)
        self.assertContains(response, '<strong>78%</strong>', html=True)
        self.assertNotContains(response, 'Overall suitability')

    @patch('employers.views.applicants.predict_suitability', return_value={'score': 0})
    def test_zero_and_missing_scores_are_distinct(self, predictor):
        self.application.match_score = None
        self.application.save(update_fields=['match_score'])
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, '<strong>Not available</strong>', html=True)
        self.assertContains(response, '<strong>0%</strong>', html=True)

    @patch('employers.views.applicants.predict_suitability')
    def test_free_recruiter_does_not_receive_pro_scores(self, predictor):
        self.profile.plan = 'free'
        self.profile.save(update_fields=['plan'])
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, 'Pro Insights')
        self.assertNotContains(response, 'compatibility-box-label')
        predictor.assert_not_called()

    @patch('employers.views.applicants.predict_suitability', return_value={'score': 78, 'label': 'Moderate predicted suitability'})
    def test_previews_link_to_separate_detail_sections(self, predictor):
        self.application.missing_skills = ['Python', 'SQL']
        self.application.matched_skills = ['Excel']
        self.application.save(update_fields=['missing_skills', 'matched_skills'])
        detail_url = reverse('recruiter_applicant_detail', args=[self.application.pk])
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, f'href="{detail_url}#skill-compatibility"')
        self.assertContains(response, f'href="{detail_url}#predicted-job-fit"')
        self.assertContains(response, 'Python, SQL')
        self.assertContains(response, 'role="tooltip"', count=2)
        detail = self.client.get(detail_url)
        self.assertContains(detail, 'id="skill-compatibility"')
        self.assertContains(detail, 'id="predicted-job-fit"')
        self.assertContains(detail, 'Python')
        self.assertContains(detail, 'Moderate predicted suitability')

    def test_other_recruiter_cannot_open_linked_application_details(self):
        other = User.objects.create_user(username='outsider-score-recruiter')
        UserProfile.objects.create(user=other, role='recruiter')
        self.client.force_login(other)
        response = self.client.get(reverse('recruiter_applicant_detail', args=[self.application.pk]))
        self.assertEqual(response.status_code, 404)

    @patch('employers.views.dashboard.predict_suitability', return_value={'score': 78, 'label': 'Moderate predicted suitability'})
    def test_dashboard_reuses_score_boxes_previews_and_detail_links(self, predictor):
        self.application.missing_skills = ['Python']
        self.application.save(update_fields=['missing_skills'])
        response = self.client.get(reverse('recruiter_dashboard'))
        detail_url = reverse('recruiter_applicant_detail', args=[self.application.pk])
        self.assertContains(response, 'recruiter-applicants-table')
        self.assertContains(response, '<strong>32%</strong>', html=True)
        self.assertContains(response, '<strong>78%</strong>', html=True)
        self.assertContains(response, f'href="{detail_url}#skill-compatibility"')
        self.assertContains(response, f'href="{detail_url}#predicted-job-fit"')
        self.assertContains(response, 'Missing Skills:')
        self.assertContains(response, 'Python')
        self.assertContains(response, 'application-status-submitted')
        self.assertNotContains(response, 'Overall suitability:')
