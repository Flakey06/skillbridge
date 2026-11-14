from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from applications.models import JobApplication

from accounts.models import UserProfile
from employers.models import Company
from jobs.models import Job
from .models import TailoredResume
from .review import review_draft, without_legacy_notes
from .services import build_tailored_resume
from .content import auto_format_resume, clean_resume_content


class ResumeReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="review-candidate")
        UserProfile.objects.create(user=self.user, role="candidate", profile_data={"name": "Candidate", "skills": "Python"})
        self.job = Job.objects.create(company=Company.objects.create(name="Employer"), created_by=self.user,
                                      title="Analyst", description="Build SQL reports for customers.",
                                      required_skills="Python, SQL", employment_type="full_time")
        self.client.force_login(self.user)

    def test_generic_summary_and_vague_bullet_are_flagged(self):
        result = review_draft("PROFESSIONAL SUMMARY\nMotivated team player.\nEXPERIENCE\n- Helped with various tasks in 2025", self.job)
        self.assertEqual(result["issue_count"], 2)
        self.assertEqual(len(result["lines"][-1]["suggestions"]), 2)

    def test_my_resume_is_generated_from_profile_without_edit_action(self):
        response = self.client.get(reverse("candidate_resume"))
        self.assertNotContains(response, ">Edit resume</a>")
        self.assertContains(response, "Automatically updated from My Profile")

    def test_quantified_specific_bullet_has_no_writing_warning(self):
        result = review_draft("EXPERIENCE\n- Built Python scripts to process 200 records for customers.", self.job)
        self.assertEqual(result["issue_count"], 0)
        self.assertIn("SQL", result["missing_skills"])
        self.assertIn("Python", result["mentioned_skills"])
        self.assertIn("Build SQL reports for customers.", result["priorities"])

    def test_copied_job_reference_does_not_count_as_candidate_evidence(self):
        result = review_draft("CORE SKILLS\nPython\nJOB DESCRIPTION PRIORITIES\nBuild SQL reports for customers.", self.job)
        self.assertIn("SQL", result["missing_skills"])

    def test_new_draft_does_not_include_internal_tailoring_notes(self):
        draft = build_tailored_resume(self.user, self.job)
        self.assertNotIn("TAILORING NOTES", draft)
        self.assertNotIn("Compatibility score:", draft)
        self.assertNotIn("EMPLOYER DETAILS USED", draft)
        self.assertNotIn("JOB DESCRIPTION PRIORITIES", draft)
        self.assertNotIn("Review every statement", draft)

    def test_cleanup_preserves_candidate_sections_after_reference_material(self):
        content = "Candidate\nCORE SKILLS\nPython\nEMPLOYER DETAILS USED\nCompany: Employer\nJOB DESCRIPTION PRIORITIES\nBuild SQL reports.\nTAILORING NOTES — REVIEW BEFORE SUBMITTING\n- Missing: SQL\nEXPERIENCE\n- Built Python scripts for 20 customers."
        cleaned = clean_resume_content(content)
        self.assertIn("Built Python scripts for 20 customers.", cleaned)
        self.assertNotIn("Company: Employer", cleaned)
        self.assertNotIn("Build SQL reports", cleaned)
        self.assertNotIn("Missing: SQL", cleaned)

    @patch("matching.services.predict_ai_compatibility", return_value=(0, {}))
    def test_old_main_resume_is_clean_in_preview_and_new_applications(self, predictor):
        content = "Candidate\nCORE SKILLS\nPython\nEMPLOYER DETAILS USED\nCompany: Employer\nJOB DESCRIPTION PRIORITIES\nSQL reports\nTAILORING NOTES — REVIEW BEFORE SUBMITTING\n- Compatibility score: 32%"
        draft = TailoredResume.objects.create(candidate=self.user, job=self.job, content=content, is_main=True)
        response = self.client.get(reverse("candidate_resume"))
        self.assertNotContains(response, "EMPLOYER DETAILS USED")
        self.assertNotContains(response, "TAILORING NOTES")
        self.assertContains(response, "Python")
        profile = self.user.profile
        profile.profile_data.update(career="technology", specialisation="backend")
        profile.save()
        response = self.client.post(reverse("job_detail", args=[self.job.pk]), {"action": "apply", "cover_note": "Interested", "resume_confirmed": "yes"})
        self.assertEqual(response.status_code, 302)
        application = JobApplication.objects.get(candidate=self.user, job=self.job)
        self.assertEqual(application.tailored_resume, "Candidate\nCORE SKILLS\nPython")
        draft.refresh_from_db()
        self.assertEqual(draft.content, content)

    def test_review_is_escaped_and_legacy_draft_changes_only_on_save(self):
        text = "SUMMARY\nMotivated <script>alert(1)</script> team player.\nTAILORING NOTES — REVIEW BEFORE SUBMITTING\n- Compatibility score: 0%"
        draft = TailoredResume.objects.create(candidate=self.user, job=self.job, content=text)
        response = self.client.get(reverse("resume_detail", args=[draft.pk]))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "Compatibility score:")
        draft.refresh_from_db()
        self.assertEqual(draft.content, text)
        updated = "SUMMARY\nAnalyst with Python experience.\nEXPERIENCE\n- Built Python reports for 20 customers."
        self.client.post(reverse("resume_detail", args=[draft.pk]), {"content": updated})
        draft.refresh_from_db()
        self.assertEqual(draft.content, updated)

    def test_direction_draft_without_job_has_writing_review(self):
        result = review_draft("SUMMARY\nMotivated team player.")
        self.assertFalse(result["has_job"])
        self.assertEqual(result["issue_count"], 1)

    def test_auto_format_normalises_headings_bullets_and_spacing_without_rewriting(self):
        content = "Candidate   Name\n\n\nexperience:\n* Built   Python reports for 20 customers.\n• Reduced review time by 10%."
        self.assertEqual(
            auto_format_resume(content),
            "Candidate Name\n\nEXPERIENCE\n- Built Python reports for 20 customers.\n- Reduced review time by 10%.",
        )

        draft = TailoredResume.objects.create(candidate=self.user, content=content)
        response = self.client.post(reverse("resume_detail", args=[draft.pk]), {
            "action": "auto_format",
            "content": content,
        })
        self.assertRedirects(response, reverse("resume_detail", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertIn("EXPERIENCE\n- Built Python reports for 20 customers.", draft.content)
