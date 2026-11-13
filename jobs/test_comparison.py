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
        self.left = Job.objects.create(title="Current Role", company=company, created_by=self.user, employment_type="full_time", status="open", moderation_status="approved")
        self.right = Job.objects.create(title="Other Role", company=company, created_by=self.user, employment_type="full_time", status="open", moderation_status="approved")
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

    def test_unapproved_job_is_not_exposed(self):
        self.right.moderation_status = "pending"
        self.right.save()
        response = self.client.get(self.url)
        self.assertNotContains(response, "Other Role")
        self.assertEqual(self.client.get(self.url, {"compare": self.right.pk}).status_code, 404)
