from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company
from jobs.models import Job
from resumes.services import build_tailored_cover_letter, build_tailored_resume

from .forms import CandidateProfileForm
from .models import CandidateMilestone, CandidateProfile, Certification
from .career_paths import career_progress


class ResumeAutofillTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = User.objects.create_user(username="autofill", password="Password123!")
        UserProfile.objects.create(user=self.user, role="candidate")
        self.client.force_login(self.user)

    def test_text_resume_autofills_blank_profile_fields(self):
        resume = SimpleUploadedFile(
            "resume.txt",
            b"Skills\nPython, Django, SQL\nExperience\nBackend intern at a fintech company\nLinkedIn https://linkedin.com/in/autofill",
            content_type="text/plain",
        )

        response = self.client.post(
            "/profile/",
            {"action": "autofill", "resume": resume},
        )

        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertIn("Python", profile.profile_data["skills"])
        self.assertEqual(profile.profile_data["career"], "technology")
        self.assertEqual(profile.profile_data["linkedin"], "https://linkedin.com/in/autofill")

    def test_resume_page_shows_feedback_for_uploaded_resume(self):
        resume = SimpleUploadedFile(
            "review.txt",
            b"Skills\nPython, Django\nExperience\nBackend intern with 20% faster API response\n",
            content_type="text/plain",
        )
        self.client.post("/profile/", {"action": "autofill", "resume": resume})

        response = self.client.get("/resume/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resume feedback")
        self.assertContains(response, "Detected skills")

    def test_saved_resume_includes_skills_portfolio_and_achievements(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.profile_data = {
            "name": "Alex Candidate",
            "skills": "Python, Django",
            "portfolio": "https://github.com/alex/project",
            "awards": "Hackathon winner",
        }
        profile.save(update_fields=["profile_data"])

        response = self.client.get("/resume/")

        self.assertContains(response, "Skills, work and achievements")
        self.assertContains(response, "Python, Django")
        self.assertContains(response, "https://github.com/alex/project")
        self.assertContains(response, "Hackathon winner")

    def test_pro_learning_shows_missing_job_skill_without_duplicate_recommendation_panel(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.plan = "pro"
        profile.profile_data = {
            "name": "Alex Candidate",
            "career": "technology",
            "specialisation": "backend",
            "skills": "Python, Django",
        }
        profile.save(update_fields=["plan", "profile_data"])
        recruiter = User.objects.create_user(username="learning_recruiter", password="Password123!")
        company = Company.objects.create(name="Learning Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Cloud Backend Engineer",
            description="Build cloud services.",
            industry="technology",
            employment_type="full_time",
            required_skills="Python, AWS",
        )
        Certification.objects.create(
            title="AWS Cloud Foundations",
            provider="AWS",
            career_area="technology",
            skills="AWS, Cloud infrastructure",
            url="https://example.com/aws",
        )

        response = self.client.get(reverse("candidate_learning"), {"job": job.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cloud Backend Engineer")
        self.assertContains(response, "AWS")
        self.assertNotContains(response, "Recommended certifications")
        self.assertNotContains(response, "AWS Cloud Foundations")


class CareerProgressTests(TestCase):
    def test_completed_certificate_is_visible_in_profile_resume_and_tailored_resume(self):
        user = User.objects.create_user(username="certificate-sync", password="testpass123")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"name": "Certificate Candidate"},
        )
        certification = Certification.objects.create(
            title="Google Data Analytics",
            provider="Google",
            career_area="technology",
        )
        CandidateMilestone.objects.create(
            candidate=user,
            certification=certification,
            status="completed",
            certificate_id="GDA-123",
            completed_at=timezone.now(),
        )
        recruiter = User.objects.create_user(username="certificate-recruiter", password="testpass123")
        company = Company.objects.create(name="Certificate Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Data Analyst",
            description="Analyse business data.",
            employment_type="full_time",
        )
        self.client.force_login(user)

        profile_response = self.client.get(reverse("candidate_profile"))
        resume_response = self.client.get(reverse("candidate_resume"))
        tailored_resume = build_tailored_resume(user, job)

        self.assertContains(profile_response, "Google Data Analytics (Certificate ID: GDA-123)")
        self.assertContains(resume_response, "Google Data Analytics (Certificate ID: GDA-123)")
        self.assertIn("Google Data Analytics (Certificate ID: GDA-123)", tailored_resume)
        self.assertEqual(
            CandidateProfile.objects.get(user=user).certifications,
            "Google Data Analytics (Certificate ID: GDA-123)",
        )
    def test_linkedin_profile_accepts_url_without_scheme(self):
        form = CandidateProfileForm(data={"linkedin": "linkedin.com/in/jamie"})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["linkedin"], "https://linkedin.com/in/jamie")

    def test_profile_combines_country_code_and_phone_number(self):
        user = User.objects.create_user(username="phone", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.post(
            "/profile/",
            {"phone_country_code": "+65", "phone": "81234567"},
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.profile_data["phone_country_code"], "+65")
        self.assertEqual(profile.profile_data["phone"], "+65 81234567")

        response = self.client.get("/profile/")
        self.assertContains(response, 'value="81234567"')

    def test_saved_profile_data_is_used_by_resume_page(self):
        user = User.objects.create_user(username="profile-resume-sync", password="testpass123")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.post(
            reverse("candidate_profile"),
            {
                "name": "Jamie Updated",
                "career": "business",
                "specialisation": "business-analysis",
                "career_stage": "beginner",
                "career_interests": ["business-analysis"],
                "education": "undergraduate",
                "institution": "nus",
                "experience": "Analysed customer data for a market research project.",
                "certifications": "Google Data Analytics",
                "skills": "Excel, SQL",
                "portfolio": "https://example.com/project",
                "awards": "Dean's list",
                "linkedin": "linkedin.com/in/jamie-updated",
                "visa": "citizen",
                "phone_country_code": "+65",
                "phone": "81234567",
                "email": "jamie@example.com",
            },
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.profile_data["name"], "Jamie Updated")
        self.assertEqual(profile.profile_data["skills"], "Excel, SQL")
        resume_response = self.client.get(reverse("candidate_resume"))
        self.assertContains(resume_response, "Jamie Updated")
        self.assertContains(resume_response, "Google Data Analytics")
        self.assertContains(resume_response, "Excel, SQL")
        self.assertContains(resume_response, "Business")
        self.assertContains(resume_response, "Business analysis")
        self.assertContains(resume_response, "National University of Singapore (NUS)")

    def test_saved_career_directions_are_used_by_skill_development(self):
        user = User.objects.create_user(username="direction-save", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career_interests": ["machine-learning"], "specialisation": "ai-ml"},
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("candidate_profile"),
            {
                "career_interests": ["software-engineering", "fintech"],
                "phone_country_code": "+65",
                "phone": "81234567",
            },
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.profile_data["career_interests"], ["software-engineering", "fintech"])

        response = self.client.get(reverse("candidate_learning"))

        self.assertContains(response, "Fintech")
        self.assertNotContains(response, 'value="machine-learning" checked')
        self.assertNotContains(response, "<strong>Machine learning</strong>", html=True)
        self.assertNotContains(response, "ai-ml")
        self.assertNotContains(response, 'value="microbiology" checked')

    def test_skill_development_shows_cards_for_profile_interests(self):
        user = User.objects.create_user(username="track-picker", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career": "technology", "career_interests": ["software-engineering", "cybersecurity"]},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("candidate_learning"))
        self.assertNotContains(response, "direction-picker-panel")
        self.assertContains(response, "Update interests")
        self.assertContains(response, "Software engineering")
        self.assertContains(response, "Open certifications")
        self.assertContains(response, "Certificate ID")

    def test_evidence_based_progress_appears_inside_skill_track(self):
        user = User.objects.create_user(username="ai-milestones", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career_interests": ["ai-engineering"], "skills": "Python"},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("candidate_learning"))

        self.assertContains(response, "AI engineering")
        self.assertContains(response, "17%")
        self.assertContains(response, "AI and programming foundations")
        self.assertNotContains(response, "Milestone summary")

    def test_progress_only_contains_selected_career_directions(self):
        user = User.objects.create_user(username="progress", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["software-engineering", "machine-learning"],
                "skills": "Python, Django",
            },
        )

        progress = career_progress(user, ["software-engineering", "machine-learning"])

        self.assertEqual([item["key"] for item in progress], ["software-engineering", "machine-learning"])
        self.assertEqual(progress[0]["percent"], 40)
        self.assertEqual(progress[1]["percent"], 20)
        self.assertTrue(progress[0]["recommendations"])
        self.assertTrue(progress[0]["missing"])
        self.assertTrue(progress[0]["milestones"])
        self.assertEqual(progress[0]["milestones"][0]["skill"], "Git")
        self.assertTrue(progress[0]["milestones"][0]["courses"])

    def test_interdisciplinary_path_has_ordered_activity_and_evidence_stages(self):
        user = User.objects.create_user(username="bioinformatics", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["bioinformatics"],
                "career_stage": "beginner",
                "skills": "Python",
            },
        )

        goal = career_progress(user, ["bioinformatics"])[0]

        self.assertEqual(goal["label"], "Bioinformatics / computational biology")
        self.assertEqual(goal["current_stage_label"], "Beginner")
        self.assertEqual(len(goal["milestones"]), 3)
        self.assertTrue(goal["milestones"][0]["activity"])
        self.assertTrue(goal["milestones"][0]["evidence"])
        self.assertTrue(goal["recommendations"])

    def test_learning_roadmap_uses_specialisation_when_directions_are_legacy(self):
        user = User.objects.create_user(username="legacy-direction", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"specialisation": "backend", "skills": "Python"},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("candidate_learning"))

        self.assertContains(response, "Software engineering")
        self.assertContains(response, "Roadmap from your current evidence")
        self.assertContains(response, "Google IT Automation with Python Professional Certificate")

    def test_uploaded_resume_evidence_changes_the_target_roadmap(self):
        with TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                user = User.objects.create_user(username="resume-roadmap", password="Password123!")
                profile = UserProfile.objects.create(
                    user=user,
                    role="candidate",
                    profile_data={"career_interests": ["software-engineering"]},
                )
                profile.resume.save(
                    "resume.txt",
                    SimpleUploadedFile(
                        "resume.txt",
                        b"Skills\nPython, Git\nExperience\nBuilt APIs with Django and SQL.",
                        content_type="text/plain",
                    ),
                    save=True,
                )

                progress = career_progress(user, ["software-engineering"])[0]

        self.assertIn("Python", progress["matched"])
        self.assertIn("Git", progress["matched"])
        self.assertNotIn("Python", progress["missing"])

    def test_completed_data_analytics_certificate_covers_foundations(self):
        user = User.objects.create_user(username="data-analytics-complete")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career_interests": ["machine-learning"]},
        )
        certificate = Certification.objects.create(
            title="Google Advanced Data Analytics Professional Certificate",
            provider="Coursera",
            career_area="machine-learning",
            skills="Python, SQL, statistics, machine learning, analytics",
        )
        CandidateMilestone.objects.create(
            candidate=user,
            certification=certificate,
            status="completed",
        )

        goal = career_progress(user, ["machine-learning"])[0]

        self.assertNotIn("SQL", goal["missing"])
        self.assertEqual(goal["milestones"][0]["status"], "completed")
        self.assertFalse(any("for SQL" in course["title"] for course in goal["recommendations"]))

    def test_unselected_direction_is_not_added_to_progress(self):
        user = User.objects.create_user(username="selected-only", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"skills": "Python"})

        progress = career_progress(user, ["marketing"])

        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]["label"], "Marketing")

    def test_certificate_submission_waits_for_verification_before_progress_updates(self):
        user = User.objects.create_user(username="course-complete", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["software-engineering"],
                "skills": "Python, Django",
            },
        )
        self.client.force_login(user)

        with TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                response = self.client.post(
                    "/learning/",
                    {
                        "action": "complete_course",
                        "career_key": "software-engineering",
                        "course_title": "Google IT Automation with Python Professional Certificate",
                        "certificate_id": "CERT-123456",
                        "verification_url": "https://www.coursera.org/account/accomplishments/verify/ABC123XYZ",
                        "evidence_file": SimpleUploadedFile(
                            "python-certificate.pdf",
                            b"%PDF-1.4 certificate evidence",
                            content_type="application/pdf",
                        ),
                    },
                )

        self.assertEqual(response.status_code, 302)
        milestone = CandidateMilestone.objects.get(candidate=user)
        self.assertEqual(milestone.status, "pending_verification")
        self.assertTrue(milestone.evidence_file)
        self.assertEqual(career_progress(user, ["software-engineering"])[0]["percent"], 40)
        milestone.status = "completed"
        milestone.save(update_fields=["status"])
        self.assertEqual(career_progress(user, ["software-engineering"])[0]["percent"], 80)

    def test_short_fake_certificate_id_is_rejected(self):
        user = User.objects.create_user(username="fake-certificate", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"career_interests": ["software-engineering"]})
        self.client.force_login(user)

        response = self.client.post("/learning/", {
            "action": "complete_course",
            "career_key": "software-engineering",
            "course_title": "Google IT Automation with Python Professional Certificate",
            "certificate_id": "abcd",
            "verification_url": "https://www.coursera.org/account/accomplishments/verify/ABC123XYZ",
            "evidence_file": SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 evidence", content_type="application/pdf"),
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CandidateMilestone.objects.filter(candidate=user).exists())

    def test_certificate_url_must_match_the_course_provider(self):
        user = User.objects.create_user(username="wrong-provider", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"career_interests": ["software-engineering"]})
        self.client.force_login(user)

        response = self.client.post("/learning/", {
            "action": "complete_course",
            "career_key": "software-engineering",
            "course_title": "Google IT Automation with Python Professional Certificate",
            "certificate_id": "CERT-123456",
            "verification_url": "https://www.credly.com/badges/11111111-1111-1111-1111-111111111111",
            "evidence_file": SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 evidence", content_type="application/pdf"),
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CandidateMilestone.objects.filter(candidate=user).exists())

    def test_coursera_share_url_creates_visible_pending_submission(self):
        user = User.objects.create_user(username="coursera-share", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"career_interests": ["software-engineering"]})
        self.client.force_login(user)

        response = self.client.post("/learning/", {
            "action": "complete_course",
            "career_key": "software-engineering",
            "course_title": "Google IT Automation with Python Professional Certificate",
            "certificate_id": "CERT-123456",
            "verification_url": "https://www.coursera.org/share/11111111-1111-1111-1111-111111111111",
            "evidence_file": SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 evidence", content_type="application/pdf"),
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 pending verification")
        self.assertContains(response, "was submitted and is pending administrator verification")
        self.assertEqual(CandidateMilestone.objects.get(candidate=user).status, "pending_verification")

        status_response = self.client.get(reverse("candidate_verification_status"))
        self.assertEqual(status_response.status_code, 200)
        certificate = status_response.json()["certificates"][0]
        self.assertEqual(certificate["status"], "pending_verification")
        self.assertEqual(certificate["title"], "Google IT Automation with Python Professional Certificate")

        withdraw_response = self.client.post("/learning/", {
            "action": "unsubmit_course",
            "course_title": "Google IT Automation with Python Professional Certificate",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json")
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertTrue(withdraw_response.json()["ok"])
        self.assertFalse(CandidateMilestone.objects.filter(candidate=user).exists())

    def test_certificate_ajax_submission_returns_status_without_redirect(self):
        user = User.objects.create_user(username="ajax-certificate", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"career_interests": ["software-engineering"]})
        self.client.force_login(user)

        response = self.client.post("/learning/", {
            "action": "complete_course",
            "career_key": "software-engineering",
            "course_title": "Google IT Automation with Python Professional Certificate",
            "certificate_id": "CERT-654321",
            "verification_url": "https://www.coursera.org/share/22222222-2222-2222-2222-222222222222",
            "evidence_file": SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 evidence", content_type="application/pdf"),
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending_verification")
        self.assertEqual(response.json()["status_label"], "Pending verification")
        self.assertNotIn("Location", response.headers)

    def test_course_cannot_be_marked_completed_without_uploaded_evidence(self):
        user = User.objects.create_user(username="course-proof", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career_interests": ["software-engineering"]},
        )
        self.client.force_login(user)

        response = self.client.post(
            "/learning/",
            {
                "action": "complete_course",
                "career_key": "software-engineering",
                "course_title": "Google IT Automation with Python Professional Certificate",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CandidateMilestone.objects.filter(candidate=user).exists())

    def test_cover_letter_prioritises_business_evidence_for_business_role(self):
        user = User.objects.create_user(username="letter", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "name": "Jamie Candidate",
                "career": "business",
                "specialisation": "business-analysis",
                "skills": "Excel, SQL",
                "portfolio": "Built a marketing dashboard that helped a retail business compare campaign performance.",
            },
        )
        recruiter = User.objects.create_user(username="letter-recruiter", password="Password123!")
        company = Company.objects.create(name="Business Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Business Analyst Intern",
            description="Gather stakeholder requirements and support market analysis.",
            industry="consulting",
            employment_type="internship",
            required_skills="Excel, SQL",
        )

        letter = build_tailored_cover_letter(user, job)

        self.assertIn("Business Analyst Intern", letter)
        self.assertIn("business-facing projects and experience", letter)
        self.assertIn("marketing dashboard", letter)

        tailored_resume = build_tailored_resume(user, job)
        self.assertIn("marketing dashboard", tailored_resume)
        self.assertNotIn("EMPLOYER DETAILS USED", tailored_resume)
        self.assertNotIn("JOB DESCRIPTION PRIORITIES", tailored_resume)
        self.assertNotIn("TAILORING NOTES", tailored_resume)

    def test_tailored_resume_contextualises_generic_coding_statement(self):
        user = User.objects.create_user(username="data-candidate", password="test-pass")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "name": "Data Candidate",
                "career": "computer science",
                "experience": "I like to code",
            },
        )
        recruiter = User.objects.create_user(username="data-recruiter", password="test-pass")
        company = Company.objects.create(name="Data Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Data Analyst",
            description="Analyse and visualise data for business decisions.",
            employment_type="full_time",
            required_skills="SQL, Excel",
        )

        tailored_resume = build_tailored_resume(user, job)

        self.assertIn("I enjoy using code to analyse and visualise data.", tailored_resume)
        self.assertNotIn("I like to code", tailored_resume)

    def test_dashboard_links_selected_directions_to_progress_page(self):
        user = User.objects.create_user(username="dashboard-progress", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["marketing"],
                "skills": "marketing, SEO",
            },
        )
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_complete"] = True
        session.save()

        response = self.client.get("/")

        self.assertContains(response, "Career readiness")
        self.assertContains(response, "40%")
        self.assertContains(response, "View Marketing roadmap")
        self.assertContains(response, "View progress and certifications")

# Create your tests here.
