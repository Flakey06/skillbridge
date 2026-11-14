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
        self.application = JobApplication.objects.create(candidate=candidate, job=job, match_score=32, match_breakdown={"resume_relevance": {"earned": 78}})
        self.client.force_login(self.recruiter)

    def test_separate_skill_snapshot_and_ml_prediction(self):
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, 'Skill Compatibility')
        self.assertContains(response, 'Predicted Job Fit')
        self.assertContains(response, '<strong>32%</strong>', html=True)
        self.assertContains(response, '<strong>78%</strong>', html=True)
        self.assertNotContains(response, 'Overall suitability')

    def test_zero_and_missing_scores_are_distinct(self):
        self.application.match_score = None
        self.application.match_breakdown = {'resume_relevance': {'earned': 0}}
        self.application.save(update_fields=['match_score', 'match_breakdown'])
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, '<strong>Not available</strong>', html=True)
        self.assertContains(response, '<strong>0%</strong>', html=True)

    def test_free_recruiter_does_not_receive_pro_scores(self):
        self.profile.plan = 'free'
        self.profile.save(update_fields=['plan'])
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, 'Pro Insights')
        self.assertNotContains(response, 'compatibility-box-label')

    def test_previews_link_to_separate_detail_sections(self):
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
        self.assertContains(detail, 'Saved resume–job prediction')

    def test_other_recruiter_cannot_open_linked_application_details(self):
        other = User.objects.create_user(username='outsider-score-recruiter')
        UserProfile.objects.create(user=other, role='recruiter')
        self.client.force_login(other)
        response = self.client.get(reverse('recruiter_applicant_detail', args=[self.application.pk]))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_reuses_score_boxes_previews_and_detail_links(self):
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

    def test_prediction_is_identical_for_both_roles_and_all_recruiter_views(self):
        from employers.models import RecruiterProfile
        RecruiterProfile.objects.create(user=self.recruiter, company=self.application.job.company)
        candidate = self.application.candidate
        UserProfile.objects.create(user=candidate, role='candidate', plan='pro', profile_data={'skills': 'Unrelated skills'})
        application = self.application
        application.match_breakdown = {'resume_relevance': {'earned': 38}}
        application.tailored_resume = 'The exact submitted resume.'
        application.save()
        # Change both live inputs: existing scores must still be the saved assessment.
        application.job.description = 'Completely changed job requirements'
        application.job.save()
        with patch('matching.ml.predict_ai_compatibility', side_effect=AssertionError('Historical application must not be rescored')):
            for url in [reverse('recruiter_applicants'), reverse('recruiter_dashboard'),
                        reverse('recruiter_applicant_detail', args=[application.pk]),
                        reverse('recruiter_compare_candidates', args=[application.pk])]:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<strong>38%</strong>', html=True)
            self.client.force_login(candidate)
            response = self.client.get(reverse('candidate_applications'))
            self.assertContains(response, '<strong>38%</strong>', html=True)

    def test_missing_prediction_is_not_replaced_by_live_profile_prediction(self):
        self.application.match_breakdown = {}
        self.application.save()
        response = self.client.get(reverse('recruiter_applicants'))
        self.assertContains(response, '<strong>Not available</strong>', html=True)
        self.assertContains(response, 'No prediction was saved')

    def test_legacy_snapshot_remains_readable_and_zero_is_preserved(self):
        self.application.match_breakdown = {'ai_match': {'earned': 0}}
        self.assertEqual(self.application.saved_job_fit, 0)
        self.application.match_breakdown = {'resume_relevance': {'earned': None}, 'ai_match': {'earned': 90}}
        self.assertIsNone(self.application.saved_job_fit)
