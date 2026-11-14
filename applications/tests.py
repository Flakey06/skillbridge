from django.test import TestCase
from django.utils import timezone

# Create your tests here.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company, RecruiterProfile
from jobs.models import Job
from resumes.models import TailoredResume

from .forms import InterviewForm
from .models import Interview, JobApplication, SavedJob


class ApplicationWorkflowTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(
            username="candidate",
            email="candidate@example.com",
            password="TestPassword123!",
        )
        UserProfile.objects.create(
            user=self.candidate,
            role="candidate",
            plan="pro",
            profile_data={
                "name": "Test Candidate",
                "career": "technology",
                "specialisation": "backend",
                "skills": "Python, Django",
            },
        )
        self.recruiter = User.objects.create_user(
            username="recruiter",
            email="recruiter@example.com",
            password="TestPassword123!",
        )
        UserProfile.objects.create(user=self.recruiter, role="recruiter")
        self.company = Company.objects.create(name="Test Company")
        RecruiterProfile.objects.create(user=self.recruiter, company=self.company)
        self.job = Job.objects.create(
            company=self.company,
            created_by=self.recruiter,
            title="Backend intern",
            description="Build Django services.",
            employment_type="internship",
            required_skills="Python, Django, JavaScript",
        )

    def test_candidate_can_apply_and_receives_match_score(self):
        self.client.force_login(self.candidate)
        response = self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "apply", "cover_note": "I am interested."},
        )

        self.assertRedirects(response, reverse("resume_detail", args=[1]))
        self.assertFalse(JobApplication.objects.filter(candidate=self.candidate, job=self.job).exists())
        self.assertContains(self.client.get(reverse("resume_detail", args=[1])), "Only an approved draft")

    def test_candidate_can_apply_with_approved_tailored_resume(self):
        tailored_resume = TailoredResume.objects.create(
            candidate=self.candidate,
            job=self.job,
            content="Approved tailored resume",
            approved_at=timezone.now(),
        )
        self.client.force_login(self.candidate)
        response = self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "apply", "cover_note": "I am interested."},
        )

        self.assertRedirects(response, reverse("candidate_applications"))
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        # Skill compatibility and evidence strength are stored separately.
        self.assertEqual(application.match_score, 67)
        self.assertEqual(application.missing_skills, ["JavaScript"])
        self.assertEqual(application.match_breakdown["skill_match"]["earned"], 67)
        self.assertEqual(application.match_breakdown["evidence_match"]["earned"], 10)
        self.assertEqual(application.tailored_resume, tailored_resume.content)

    def test_free_candidate_can_submit_without_a_pro_match_object(self):
        self.candidate.profile.plan = "free"
        self.candidate.profile.save(update_fields=["plan"])
        resume = TailoredResume.objects.create(
            candidate=self.candidate,
            title="Free candidate resume",
            content="Python and Django experience",
            approved_at=timezone.now(),
        )
        self.client.force_login(self.candidate)
        response = self.client.post(reverse("job_detail", args=[self.job.pk]), {
            "action": "apply",
            "cover_note": "I am interested.",
            "resume_id": resume.pk,
        })
        self.assertRedirects(response, reverse("candidate_applications"))
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.assertIsNotNone(application.match_score)
        self.assertIn("Python", application.matched_skills)

    def test_candidate_application_submits_saved_tailored_resume(self):
        TailoredResume.objects.create(
            candidate=self.candidate,
            job=self.job,
            title="Backend application draft",
            content="My edited tailored resume",
            approved_at=timezone.now(),
        )
        self.client.force_login(self.candidate)

        response = self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "apply", "cover_note": "I am interested."},
        )

        self.assertRedirects(response, reverse("candidate_applications"))
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.assertEqual(application.tailored_resume, "My edited tailored resume")

    def test_candidate_can_choose_which_approved_resume_to_submit(self):
        default_resume = TailoredResume.objects.create(
            candidate=self.candidate,
            job=self.job,
            title="Default job resume",
            content="Default resume content",
            approved_at=timezone.now(),
        )
        chosen_resume = TailoredResume.objects.create(
            candidate=self.candidate,
            title="Chosen general resume",
            content="Chosen resume content with Python and Django evidence",
            approved_at=timezone.now(),
        )
        self.client.force_login(self.candidate)

        page = self.client.get(reverse("job_detail", args=[self.job.pk]))
        self.assertContains(page, "Resume to submit")
        self.assertContains(page, "Chosen general resume")
        self.assertContains(page, "Pro recommendation: Chosen general resume")
        self.assertContains(page, "AI compatibility")
        self.assertContains(page, "For your highest-scoring resume")
        self.assertContains(page, "Compare another resume")
        self.assertContains(page, "% predicted fit")
        self.assertContains(page, "Recommended")
        self.assertNotContains(page, "Tailor my resume")
        response = self.client.post(reverse("job_detail", args=[self.job.pk]), {
            "action": "apply",
            "cover_note": "I am interested.",
            "resume_id": chosen_resume.id,
        })

        self.assertRedirects(response, reverse("candidate_applications"))
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.assertEqual(application.tailored_resume, "Chosen resume content with Python and Django evidence")
        self.assertNotEqual(application.tailored_resume, default_resume.content)

    def test_candidate_can_confirm_unreviewed_resume_and_apply_without_leaving_job(self):
        resume = TailoredResume.objects.create(
            candidate=self.candidate,
            title="Resume ready to check",
            content="Python and Django project evidence",
        )
        self.client.force_login(self.candidate)

        response = self.client.post(reverse("job_detail", args=[self.job.pk]), {
            "action": "apply",
            "cover_note": "I reviewed this cover letter.",
            "resume_id": resume.id,
            "resume_confirmed": "yes",
        })

        self.assertRedirects(response, reverse("candidate_applications"))
        resume.refresh_from_db()
        self.assertIsNotNone(resume.approved_at)
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.assertEqual(application.tailored_resume, "Python and Django project evidence")

    def test_recruiter_can_update_status_and_schedule_interview(self):
        JobApplication.objects.create(candidate=self.candidate, job=self.job)
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.client.force_login(self.recruiter)

        response = self.client.post(
            reverse("recruiter_applicants"),
            {"application_id": application.pk, "status": "shortlisted"},
        )
        self.assertRedirects(response, reverse("recruiter_calendar") + f"?application={application.pk}")
        application.refresh_from_db()
        self.assertEqual(application.status, "shortlisted")

        response = self.client.post(
            reverse("recruiter_calendar"),
            {
                "application_id": application.pk,
                "scheduled_start": "2026-10-22T14:00",
                "meeting_url": "cal.com/interview",
                "notes": "Technical discussion",
            },
        )
        self.assertRedirects(response, reverse("recruiter_calendar"))
        self.assertEqual(Interview.objects.filter(application=application).count(), 1)
        self.assertEqual(self.client.get(reverse("recruiter_calendar")).status_code, 200)

        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(reverse("candidate_calendar")).status_code, 200)

    def test_candidate_only_sees_open_jobs(self):
        draft_job = Job.objects.create(
            company=self.company,
            created_by=self.recruiter,
            title="Hidden draft",
            description="Not published yet.",
            employment_type="internship",
            status="draft",
        )
        self.client.force_login(self.candidate)

        response = self.client.get(reverse("candidate_jobs"))

        self.assertNotContains(response, draft_job.title)
        self.assertContains(response, self.job.title)

    def test_candidate_can_star_and_unstar_a_job(self):
        self.client.force_login(self.candidate)

        response = self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "save"},
        )
        self.assertRedirects(response, reverse("job_detail", args=[self.job.pk]))
        self.assertTrue(SavedJob.objects.filter(candidate=self.candidate, job=self.job).exists())

        response = self.client.get(reverse("job_detail", args=[self.job.pk]))
        self.assertContains(response, "star-action saved")

        self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "unsave"},
        )
        self.assertFalse(SavedJob.objects.filter(candidate=self.candidate, job=self.job).exists())

    def test_candidate_needs_essential_profile_details_before_applying(self):
        self.candidate.profile.profile_data = {"skills": "Python, Django"}
        self.candidate.profile.save(update_fields=["profile_data"])
        self.client.force_login(self.candidate)

        response = self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "apply", "cover_note": "Interested."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete your essential profile first")
        self.assertFalse(JobApplication.objects.filter(candidate=self.candidate, job=self.job).exists())

    def test_calcom_url_without_scheme_is_normalised(self):
        form = InterviewForm(
            data={
                "scheduled_start": "2026-10-22T14:00",
                "meeting_url": "cal.com/interview",
                "calcom_event_url": "cal.com/event",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["meeting_url"], "https://cal.com/interview")
        self.assertEqual(form.cleaned_data["calcom_event_url"], "https://cal.com/event")
