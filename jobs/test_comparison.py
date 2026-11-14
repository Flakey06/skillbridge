from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company
from jobs.models import Job


class JobComparisonTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="comparison-candidate")
        UserProfile.objects.create(user=self.user, role="candidate")
        company = Company.objects.create(name="Comparison Company")
        self.left = Job.objects.create(title="Current Role", company=company, created_by=self.user, employment_type="full_time", status="open")
        self.right = Job.objects.create(title="Other Role", company=company, created_by=self.user, employment_type="full_time", status="open")
        self.url = reverse("job_compare", args=[self.left.pk])
        self.client.force_login(self.user)

    def test_current_job_and_selected_comparison_render(self):
        response = self.client.get(self.url, {"compare": self.right.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["comparison_job"], self.right)
        self.assertContains(response, "Current Role")
        self.assertContains(response, "Other Role")
        self.assertNotIn(self.left, response.context["comparison_choices"])

    def test_closed_job_cannot_be_selected(self):
        self.right.status = "closed"
        self.right.save()
        self.assertEqual(self.client.get(self.url, {"compare": self.right.pk}).status_code, 404)

    def test_new_open_job_is_available_without_approval(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Other Role")
        self.assertEqual(self.client.get(self.url, {"compare": self.right.pk}).status_code, 200)

    def test_detail_breakdown_explains_compared_resume_not_main_resume(self):
        from unittest.mock import patch
        from resumes.models import TailoredResume
        profile = self.user.profile
        profile.plan = 'pro'
        profile.save()
        self.left.required_skills = 'Python'
        self.left.save()
        TailoredResume.objects.create(candidate=self.user, title='Main', content='No relevant evidence', is_main=True)
        selected = TailoredResume.objects.create(candidate=self.user, title='Python Resume', content='Python project internship')
        with patch('matching.services.predict_ai_compatibility', return_value=(41, {})):
            response = self.client.get(reverse('job_detail', args=[self.left.pk]), {'compare_resume': selected.pk})
        self.assertEqual(response.status_code, 200)
        comparison = response.context['comparison_resume']
        breakdown = response.context['detail_match']
        self.assertEqual(breakdown['score'], comparison['skill_score'])
        self.assertEqual(breakdown['matched_skills'], comparison['matched_skills'])
        self.assertEqual(breakdown['score_breakdown'], comparison['breakdown'])
        self.assertContains(response, 'Skills And Evidence Breakdown')
        self.assertNotContains(response, 'Resume comparison above assesses the selected version.')
