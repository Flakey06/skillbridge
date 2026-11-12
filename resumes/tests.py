from django.test import TestCase

from accounts.models import UserProfile
from employers.models import Company
from jobs.models import Job

from .models import TailoredResume
from django.contrib.auth.models import User


class TailoredResumeWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="candidate", password="test-pass")
        UserProfile.objects.create(
            user=self.user,
            role="candidate",
            profile_data={"name": "Candidate"},
        )
        recruiter = User.objects.create_user(username="recruiter", password="test-pass")
        company = Company.objects.create(name="Example Company")
        self.job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Software Engineer",
            description="Build software.",
            employment_type="full_time",
        )

    def test_tailored_resume_can_be_edited_and_saved(self):
        tailored_resume = TailoredResume.objects.create(
            candidate=self.user,
            job=self.job,
            title="Resume for Software Engineer",
            content="Original draft",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            f"/resumes/{tailored_resume.id}/",
            {
                "title": "Updated application resume",
                "content": "Updated resume content",
            },
        )

        self.assertRedirects(response, f"/resumes/{tailored_resume.id}/")
        tailored_resume.refresh_from_db()
        self.assertEqual(tailored_resume.title, "Updated application resume")
        self.assertEqual(tailored_resume.content, "Updated resume content")
        self.assertIsNone(tailored_resume.approved_at)

    def test_tailored_resume_can_be_approved_after_review(self):
        tailored_resume = TailoredResume.objects.create(
            candidate=self.user,
            job=self.job,
            content="Reviewed resume",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            f"/resumes/{tailored_resume.id}/",
            {
                "action": "approve",
                "title": tailored_resume.title,
                "content": tailored_resume.content,
            },
        )

        self.assertRedirects(response, f"/resumes/{tailored_resume.id}/")
        tailored_resume.refresh_from_db()
        self.assertIsNotNone(tailored_resume.approved_at)
