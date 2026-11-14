from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from employers.models import Company
from jobs.models import Job
from .models import Notification, SiteFeedback, UserProfile


class FeedbackTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(username="feedback-candidate")
        UserProfile.objects.create(user=self.candidate, role="candidate")
        self.recruiter = User.objects.create_user(username="feedback-recruiter")
        UserProfile.objects.create(user=self.recruiter, role="recruiter")
        self.staff = User.objects.create_user(username="feedback-admin", is_staff=True)
        self.company = Company.objects.create(name="Feedback Company")
        self.job = Job.objects.create(
            title="Feedback Role", company=self.company, created_by=self.recruiter,
            employment_type="full_time", description="A role open to feedback.",
        )

    def test_candidate_can_submit_job_feedback(self):
        self.client.force_login(self.candidate)
        response = self.client.post(reverse("feedback"), {
            "category": "job", "job": self.job.pk, "rating": "4",
            "message": "Please make the responsibilities clearer.",
        })
        self.assertRedirects(response, reverse("feedback"))
        item = SiteFeedback.objects.get()
        self.assertEqual(item.user, self.candidate)
        self.assertEqual(item.job, self.job)
        self.assertEqual(item.rating, 4)

    def test_job_feedback_requires_a_job(self):
        self.client.force_login(self.candidate)
        response = self.client.post(reverse("feedback"), {
            "category": "job", "message": "This should identify the listing.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose the job this feedback is about.")
        self.assertFalse(SiteFeedback.objects.exists())

    def test_recruiter_only_sees_own_jobs_in_feedback_form(self):
        other = User.objects.create_user(username="other-recruiter")
        UserProfile.objects.create(user=other, role="recruiter")
        other_job = Job.objects.create(title="Other Role", company=self.company, created_by=other, employment_type="full_time")
        self.client.force_login(self.recruiter)
        response = self.client.get(reverse("feedback"))
        choices = list(response.context["form"].fields["job"].queryset)
        self.assertIn(self.job, choices)
        self.assertNotIn(other_job, choices)

    def test_candidate_feedback_hides_unpublished_job(self):
        draft = Job.objects.create(
            title="Private Draft", company=self.company, created_by=self.recruiter,
            employment_type="full_time", status="draft",
        )
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("feedback"))
        self.assertNotIn(draft, response.context["form"].fields["job"].queryset)

    def test_admin_can_reply_and_user_is_notified(self):
        item = SiteFeedback.objects.create(user=self.candidate, category="feature", message="Add clearer interview guidance.")
        self.client.force_login(self.staff)
        response = self.client.post(reverse("administration_review_feedback", args=[item.pk]), {
            "decision": "reviewed", "response": "Thanks, we are reviewing this improvement.",
        })
        self.assertRedirects(response, reverse("administration_dashboard") + "?section=reports")
        item.refresh_from_db()
        self.assertEqual(item.status, "reviewed")
        self.assertEqual(item.reviewed_by, self.staff)
        self.assertTrue(Notification.objects.filter(recipient=self.candidate, kind="feedback").exists())
        self.client.post(reverse("administration_review_feedback", args=[item.pk]), {
            "decision": "closed", "response": "Completed.",
        })
        item.refresh_from_db()
        self.assertEqual(item.status, "closed")
