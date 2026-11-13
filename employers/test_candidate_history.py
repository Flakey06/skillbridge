from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from applications.models import (
    ApplicantEvaluation,
    ApplicationReviewEvent,
    CandidateCompanyBlacklist,
    JobApplication,
)
from jobs.models import Job

from .models import Company, RecruiterProfile


class RecruiterCandidateHistoryTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user("history-recruiter", password="password")
        UserProfile.objects.create(user=self.recruiter, role="recruiter")
        self.company = Company.objects.create(name="History Co")
        RecruiterProfile.objects.create(user=self.recruiter, company=self.company)
        self.candidate = User.objects.create_user("repeat-candidate", password="password")
        UserProfile.objects.create(
            user=self.candidate,
            role="candidate",
            profile_data={"name": "Repeat Candidate", "career": "technology", "specialisation": "backend"},
        )
        self.jobs = [
            Job.objects.create(
                company=self.company,
                created_by=self.recruiter,
                title=title,
                description="Test role",
                employment_type="full_time",
            )
            for title in ("First role", "Second role", "Future role")
        ]
        self.applications = [
            JobApplication.objects.create(candidate=self.candidate, job=job, status="rejected")
            for job in self.jobs[:2]
        ]
        self.client.force_login(self.recruiter)

    def test_repeat_failure_filter_shows_company_counts(self):
        response = self.client.get(reverse("recruiter_applicants"), {"history": "repeat_rejections"})

        self.assertEqual(response.status_code, 200)
        applications = list(response.context["applications"])
        self.assertEqual(len(applications), 2)
        self.assertTrue(all(item.company_application_count == 2 for item in applications))
        self.assertTrue(all(item.company_rejection_count == 2 for item in applications))

    def test_status_changes_create_review_history(self):
        application = self.applications[0]
        response = self.client.post(
            reverse("recruiter_applicant_detail", args=[application.pk]),
            {"status": "shortlisted", "review_note": "Strong portfolio on second review."},
        )

        self.assertEqual(response.status_code, 302)
        event = ApplicationReviewEvent.objects.get(application=application)
        self.assertEqual(event.previous_status, "rejected")
        self.assertEqual(event.new_status, "shortlisted")
        self.assertEqual(event.note, "Strong portfolio on second review.")

    def test_permanent_blacklist_blocks_future_company_applications(self):
        application = self.applications[0]
        response = self.client.post(
            reverse("recruiter_applicant_detail", args=[application.pk]),
            {"action": "blacklist", "blacklist_reason": "Repeated failed screening reviews."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CandidateCompanyBlacklist.objects.filter(
            company=self.company, candidate=self.candidate
        ).exists())

        self.client.force_login(self.candidate)
        response = self.client.get(reverse("job_detail", args=[self.jobs[2].pk]))
        self.assertContains(response, "You cannot apply to roles at this company.")
        self.assertContains(response, "Applications unavailable")

    def test_structured_survey_creates_fixed_score_and_filter(self):
        application = self.applications[0]
        response = self.client.post(
            reverse("recruiter_applicant_detail", args=[application.pk]),
            {
                "action": "save_evaluation",
                "skills_score": "5",
                "experience_score": "4",
                "evidence_score": "3",
                "role_readiness_score": "4",
                "recommendation": "yes",
                "notes": "Consistent evidence across the application.",
            },
        )

        self.assertEqual(response.status_code, 302)
        evaluation = ApplicantEvaluation.objects.get(application=application)
        self.assertEqual(evaluation.total_score, 80)
        self.assertEqual(evaluation.reviewed_by, self.recruiter)

        application.match_score = 85
        application.save(update_fields=["match_score"])
        response = self.client.get(reverse("recruiter_applicants"), {"min_ats_score": "80"})
        applications = list(response.context["applications"])
        self.assertEqual(applications, [application])
        self.assertContains(response, "85/100")
        self.assertContains(response, "Automatic application match")

