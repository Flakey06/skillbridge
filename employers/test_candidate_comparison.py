from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from applications.models import JobApplication
from employers.models import Company
from jobs.models import Job


class CandidateComparisonTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(username="comparison-recruiter")
        UserProfile.objects.create(user=self.recruiter, role="recruiter")
        company = Company.objects.create(name="Comparison Employer")
        self.job = Job.objects.create(title="Engineer", company=company, created_by=self.recruiter, employment_type="full_time")
        self.candidates = [User.objects.create_user(username=f"candidate-{i}") for i in range(3)]
        for candidate in self.candidates:
            UserProfile.objects.create(user=candidate, role="candidate")
        self.left = JobApplication.objects.create(candidate=self.candidates[0], job=self.job)
        self.right = JobApplication.objects.create(candidate=self.candidates[1], job=self.job)
        self.url = reverse("recruiter_compare_candidates", args=[self.left.pk])
        self.client.force_login(self.recruiter)

    def test_same_job_comparison_renders(self):
        response = self.client.get(self.url, {"compare": self.right.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "candidate-0")
        self.assertContains(response, "candidate-1")
        self.assertEqual(list(response.context["comparison_choices"]), [self.right])
        self.assertNotContains(response, "Predicted Job Fit")

    def test_different_job_application_is_rejected(self):
        other_job = Job.objects.create(title="Other Job", company=self.job.company, created_by=self.recruiter, employment_type="full_time")
        other = JobApplication.objects.create(candidate=self.candidates[2], job=other_job)
        self.assertEqual(self.client.get(self.url, {"compare": other.pk}).status_code, 404)

    def test_other_recruiter_cannot_access_comparison(self):
        other = User.objects.create_user(username="other-comparison-recruiter")
        UserProfile.objects.create(user=other, role="recruiter")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
