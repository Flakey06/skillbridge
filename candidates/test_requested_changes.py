import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from applications.models import JobApplication, SavedJob
from employers.models import Company
from jobs.models import Job
from resumes.models import TailoredResume
from candidates.views import _completion_percent
from candidates.forms import CandidateProfileForm


@patch("matching.services.predict_ai_compatibility", side_effect=lambda resume, job, score: (score, {"mode": "skill_fallback"}))
class RequestedWorkflowTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.override.disable)
        self.candidate = User.objects.create_user(username="candidate")
        self.profile = UserProfile.objects.create(user=self.candidate, role="candidate", profile_data={
            "skills": "Python", "career_interests": ["software-engineering"],
        })
        self.recruiter = User.objects.create_user(username="recruiter")
        UserProfile.objects.create(user=self.recruiter, role="recruiter", plan="pro")
        company = Company.objects.create(name="Company")
        self.high = Job.objects.create(company=company, created_by=self.recruiter, title="Older Python job", description="Python", required_skills="Python", employment_type="full_time")
        self.low = Job.objects.create(company=company, created_by=self.recruiter, title="Newer Java job", description="Java", required_skills="Java", employment_type="full_time")
        self.client.force_login(self.candidate)

    def test_pro_can_sort_jobs_by_score_while_free_keeps_newest(self, predictor):
        url = reverse("candidate_jobs")
        response = self.client.get(url, {"sort": "match"})
        self.assertEqual(response.context["job_cards"][0]["job"], self.low)
        self.profile.plan = "pro"
        self.profile.save()
        response = self.client.get(url, {"sort": "match"})
        self.assertEqual(response.context["job_cards"][0]["job"], self.high)
        response = self.client.get(url, {"sort": "match", "q": "Java"})
        self.assertEqual([card["job"] for card in response.context["job_cards"]], [self.low])

    def test_name_edit_keeps_completion_and_updates_dashboard_display_name(self, predictor):
        self.profile.profile_data = {"name": "jj", "career": "business", "specialisation": "fintech", "skills": "Python"}
        self.profile.save()
        before = _completion_percent(self.profile)
        initial = CandidateProfileForm(initial=self.profile.profile_data)
        self.assertIn("fintech", dict(initial.fields["specialisation"].choices))
        response = self.client.post(reverse("candidate_profile"), {
            "name": "james", "career": "business", "specialisation": "fintech", "skills": "Python",
        })
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_name, "james")
        self.assertEqual(self.profile.initials, "JA")
        self.assertEqual(_completion_percent(self.profile), before)
        self.assertContains(self.client.get(reverse("home")), '<span class="preserve-case">james</span>')

    def test_manual_profile_controls_and_legacy_autosave_endpoint(self, predictor):
        page = self.client.get(reverse("candidate_profile"))
        self.assertContains(page, "Save Profile")
        self.assertNotContains(page, "<script")
        self.assertNotContains(page, "Upload selected files")
        self.assertNotContains(page, ">Save profile<")

        response = self.client.post(reverse("candidate_profile"), {
            "action": "autosave",
            "name": "Jamie Tan",
            "skills": "Python, Django",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "All changes saved automatically")
        self.assertFalse(payload["application_ready"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data["name"], "Jamie Tan")
        self.assertEqual(self.profile.profile_data["skills"], "Python, Django")
        main_resume = TailoredResume.objects.get(candidate=self.candidate, is_main=True)
        self.assertIn("Jamie Tan", main_resume.content)
        self.assertIn("Python, Django", main_resume.content)

        self.client.post(reverse("candidate_profile"), {
            "action": "autosave",
            "name": "Jamie Tan",
            "skills": "Python, Django, SQL",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        main_resume.refresh_from_db()
        self.assertIn("Python, Django, SQL", main_resume.content)

        main_resume.content = "Stale resume content"
        main_resume.save(update_fields=["content"])
        resume_page = self.client.get(reverse("candidate_resume"))
        self.assertContains(resume_page, "Automatically updated from My Profile")
        self.assertContains(resume_page, "Python, Django, SQL")
        self.assertContains(resume_page, "Resume timeline")
        self.assertContains(resume_page, "Main profile resume")
        self.assertContains(resume_page, "v20")
        main_resume.refresh_from_db()
        self.assertNotEqual(main_resume.content, "Stale resume content")

        job_resume = TailoredResume.objects.create(
            candidate=self.candidate,
            job=self.high,
            title="Resume for Older Python job",
            content="Job-specific resume",
        )
        resume_page = self.client.get(reverse("candidate_resume"))
        self.assertContains(resume_page, "Edit resume")
        self.assertNotContains(resume_page, "Resume type and version")
        selector_page = self.client.get(reverse("candidate_resume_select"), {
            "resume_id": job_resume.id,
        })
        self.assertContains(selector_page, "Resume type and version")
        self.assertContains(selector_page, "Job application")
        self.assertContains(selector_page, "Job-specific resume")
        self.assertContains(selector_page, "Edit this resume")
        self.assertContains(selector_page, "Make main resume")
        main_response = self.client.post(reverse("set_main_resume", args=[job_resume.id]))
        self.assertRedirects(main_response, reverse("candidate_resume"))
        job_resume.refresh_from_db()
        self.assertTrue(job_resume.is_main)

        upload_response = self.client.post(reverse("candidate_profile"), {
            "action": "auto_upload",
            "resume": SimpleUploadedFile(
                "automatic-resume.txt",
                b"Jamie Tan\nPython and Django experience",
                content_type="text/plain",
            ),
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(upload_response.status_code, 200)
        self.assertEqual(upload_response.json()["message"], "File uploaded and all changes saved")
        self.profile.refresh_from_db()
        self.assertIn("automatic-resume", self.profile.resume.name)

    def test_required_application_profile_fields_autosave_together(self, predictor):
        response = self.client.post(reverse("candidate_profile_autosave"), {
            "action": "autosave",
            "name": "Jamie Candidate",
            "career": "technology",
            "specialisation": "software-engineering",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["application_ready"])
        self.assertEqual(payload["missing_required"], [])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data["name"], "Jamie Candidate")
        self.assertEqual(self.profile.profile_data["career"], "technology")
        self.assertEqual(self.profile.profile_data["specialisation"], "software-engineering")

    def test_removing_all_experience_and_certifications_persists(self, predictor):
        self.profile.profile_data = {
            "experience": "Previous experience", "experience_entries": [{"position": "Intern"}],
            "certifications": "Previous certificate", "certification_entries": [{"name": "Course"}],
        }
        self.profile.save()
        response = self.client.post(reverse("candidate_profile"), {
            "experience": "", "experience_entries": "[]",
            "certifications": "", "certification_entries": "[]",
        })
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data["experience_entries"], [])
        self.assertEqual(self.profile.profile_data["certification_entries"], [])
        self.assertEqual(self.profile.profile_data["experience"], "")
        self.assertEqual(self.profile.profile_data["certifications"], "")

    def test_validation_error_returns_scroll_and_expanded_section_state(self, predictor):
        response = self.client.post(reverse("candidate_profile"), {
            "linkedin": "https://example.com/not-linkedin",
            "profile_scroll_y": "1250", "profile_open_sections": "[false,true]",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, 'data-restore-scroll="1250"')
        self.assertContains(response, 'data-restore-sections="[false,true]"')

    def test_applied_status_is_shared_across_cards_and_detail(self, predictor):
        JobApplication.objects.create(candidate=self.candidate, job=self.high)
        SavedJob.objects.create(candidate=self.candidate, job=self.high)
        jobs = self.client.get(reverse("candidate_jobs"))
        flags = {card["job"].pk: card["has_applied"] for card in jobs.context["job_cards"]}
        self.assertTrue(flags[self.high.pk])
        self.assertFalse(flags[self.low.pk])
        dashboard = self.client.get(reverse("home"))
        self.assertTrue(next(job for job in dashboard.context["recent_jobs"] if job.pk == self.high.pk).has_applied)
        self.assertTrue(self.client.get(reverse("candidate_saved_jobs")).context["job_cards"][0]["has_applied"])
        detail = self.client.get(reverse("job_detail", args=[self.high.pk]))
        self.assertContains(detail, 'disabled>Already Applied</button>')
        self.assertNotContains(detail, 'form="job-application-form"')
        self.client.post(reverse("job_detail", args=[self.high.pk]), {"action": "apply"})
        self.assertEqual(JobApplication.objects.filter(candidate=self.candidate, job=self.high).count(), 1)

    def test_saving_stays_on_list_and_saved_state_is_shared_across_pages(self, predictor):
        next_url = reverse("candidate_jobs") + "?q=Python&sort=match"
        url = reverse("job_save", args=[self.high.pk])
        response = self.client.post(url, {"action": "save", "next": next_url})
        self.assertEqual(response.url, next_url)
        self.client.post(url, {"action": "save", "next": next_url})
        self.assertEqual(SavedJob.objects.filter(candidate=self.candidate, job=self.high).count(), 1)
        dashboard = self.client.get(reverse("home"))
        self.assertTrue(next(job for job in dashboard.context["recent_jobs"] if job.pk == self.high.pk).is_saved)
        self.assertContains(dashboard, 'aria-pressed="true"')
        jobs = self.client.get(reverse("candidate_jobs"))
        self.assertTrue(next(card for card in jobs.context["job_cards"] if card["job"].pk == self.high.pk)["is_saved"])
        saved = self.client.get(reverse("candidate_saved_jobs"))
        self.assertEqual(saved.context["job_cards"][0]["job"], self.high)
        self.assertTrue(self.client.get(reverse("job_detail", args=[self.high.pk])).context["is_saved"])
        response = self.client.post(url, {"action": "unsave", "next": reverse("home")})
        self.assertEqual(response.url, reverse("home"))
        dashboard = self.client.get(reverse("home"))
        self.assertFalse(next(job for job in dashboard.context["recent_jobs"] if job.pk == self.high.pk).is_saved)
        self.assertFalse(self.client.get(reverse("candidate_saved_jobs")).context["job_cards"])

    def test_save_control_is_post_only_and_rejects_external_return_urls(self, predictor):
        url = reverse("job_save", args=[self.high.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {"action": "save", "next": "https://example.com/"})
        self.assertEqual(response.url, reverse("candidate_jobs"))
        self.client.force_login(self.recruiter)
        self.assertEqual(self.client.post(url, {"action": "unsave"}).status_code, 302)
        self.assertTrue(SavedJob.objects.filter(candidate=self.candidate, job=self.high).exists())

    def test_async_save_returns_persisted_status_and_count_without_redirect(self, predictor):
        url = reverse("job_save", args=[self.high.pk])
        response = self.client.post(url, {"action": "save"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"job_id": self.high.pk, "is_saved": True, "saved_count": 1})
        self.assertTrue(SavedJob.objects.filter(candidate=self.candidate, job=self.high).exists())
        response = self.client.post(url, {"action": "unsave"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"job_id": self.high.pk, "is_saved": False, "saved_count": 0})
        self.assertFalse(SavedJob.objects.filter(candidate=self.candidate, job=self.high).exists())

    def test_recruiter_sort_uses_application_snapshot_and_nulls_last(self, predictor):
        low = JobApplication.objects.create(candidate=self.candidate, job=self.low, match_score=10)
        high = JobApplication.objects.create(candidate=self.candidate, job=self.high, match_score=90)
        other = User.objects.create_user(username="no-score")
        missing = JobApplication.objects.create(candidate=other, job=self.high)
        self.client.force_login(self.recruiter)
        url = reverse("recruiter_applicants")
        response = self.client.get(url, {"sort": "match"})
        self.assertEqual(list(response.context["applications"]), [high, low, missing])
        self.recruiter.profile.plan = "free"
        self.recruiter.profile.save()
        response = self.client.get(url, {"sort": "match"})
        self.assertEqual(list(response.context["applications"]), [missing, high, low])

    def test_equal_skill_scores_use_newest_order_even_when_ai_scores_differ(self, predictor):
        self.profile.plan = "pro"
        self.profile.profile_data = {"skills": "SQL"}
        self.profile.save()
        predictor.side_effect = lambda resume, job, score: (99 if "Python" in job else 1, {"mode": "dataset"})
        response = self.client.get(reverse("candidate_jobs"), {"sort": "match"})
        cards = response.context["job_cards"]
        self.assertEqual(cards[0]["match"].score, cards[1]["match"].score)
        self.assertEqual([card["job"] for card in cards], [self.low, self.high])
        self.assertContains(response, "Equal scores are ordered newest first")

    def test_job_without_skill_requirements_shows_unavailable_ai_score(self, predictor):
        self.profile.plan = "pro"
        self.profile.save()
        self.low.required_skills = ""
        self.low.description = "Help the team."
        self.low.title = "General role"
        self.low.save()
        response = self.client.get(reverse("candidate_jobs"), {"q": "General role"})
        self.assertContains(response, "Not available")
        self.assertContains(response, "listing needs skill requirements")

    def test_unsuitable_autofill_does_not_replace_existing_file_or_data(self, predictor):
        self.profile.resume.save("existing.txt", SimpleUploadedFile("existing.txt", b"Original resume text"))
        previous_name = self.profile.resume.name
        response = self.client.post(reverse("candidate_profile"), {
            "action": "autofill", "resume": SimpleUploadedFile("article.txt", b"An unrelated article about weather."),
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.resume.name, previous_name)
        self.assertEqual(self.profile.profile_data["skills"], "Python")

    def test_suitable_autofill_is_accepted(self, predictor):
        text = """Taylor Candidate
taylor@example.com
Education
Bachelor of Science, National University of Singapore, 2024
Skills
Python SQL Git Django JavaScript
Experience
Software engineer intern, 2025
Developed Python web services and database queries for a university project with a team of students.
"""
        self.client.post(reverse("candidate_profile"), {"action": "autofill", "resume": SimpleUploadedFile("resume.txt", text.encode())})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.resume)
        self.assertEqual(self.profile.profile_data["name"], "Taylor Candidate")

    def test_partial_skill_evidence_is_not_silently_discarded(self, predictor):
        response = self.client.post(reverse("tailor_resume_for_interest", args=["software-engineering"]), {"description_Python": "Built a data cleaning script."})
        self.assertContains(response, "provide both your experience and duration")
        self.assertContains(response, "Built a data cleaning script.")
        self.assertFalse(TailoredResume.objects.exists())

    def test_learning_route_and_self_reported_evidence_are_explicit(self, predictor):
        response = self.client.get(reverse("tailor_resume_for_interest", args=["software-engineering"]))
        self.assertContains(response, "self-reported, not independently verified")
        self.assertContains(response, "explore courses and activities")
        self.client.post(reverse("tailor_resume_for_interest", args=["software-engineering"]), {
            "description_Python": "Built a data cleaning script.", "duration_Python": "Two weeks",
        })
        self.assertIn("Python — Built a data cleaning script. (Two weeks)", TailoredResume.objects.get().content)
