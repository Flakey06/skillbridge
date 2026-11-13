import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .forms import SignupForm
from .models import Payment, Referral, UserProfile
from .payment_services import set_stripe_entitlement
from .models import Notification


class AccountOnboardingTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)

    def test_login_shows_red_error_for_invalid_credentials(self):
        response = self.client.post(
            reverse("login"),
            {"username": "unknown", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username/email or password.")
        self.assertContains(response, 'class="errorlist nonfield"')

    def test_login_page_links_to_signup(self):
        response = self.client.get(f"{reverse('login')}?next=/plans/")

        self.assertContains(response, "Create an account")
        self.assertContains(response, f'{reverse("signup")}?next=/plans/')

    def test_profile_initials_use_onboarding_name(self):
        user = UserProfile.objects.create(
            user=self._create_user("candidate"),
            role="candidate",
            profile_data={"name": "Alex Tan"},
        )

        self.assertEqual(user.initials, "AT")

    def _create_user(self, username):
        from django.contrib.auth.models import User

        return User.objects.create_user(username=username, password="password")

    def test_signup_does_not_collect_name(self):
        self.assertNotIn("first_name", SignupForm.base_fields)
        self.assertNotIn("last_name", SignupForm.base_fields)

    def test_candidate_onboarding_starts_with_resume_upload(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "candidate",
                "email": "candidate@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )

        self.assertRedirects(response, reverse("onboarding"))
        response = self.client.get(reverse("onboarding"))

        self.assertContains(response, "How would you like to build your resume?")
        self.assertContains(response, 'type="file"')
        self.assertContains(response, "multipart/form-data")
        self.assertContains(response, "Skip for now")
        self.assertContains(response, "Submit resume &amp; auto-fill")
        self.assertContains(response, "Sandy validates it before filling the editable fields")
        self.assertContains(response, "Fill it in myself")
        self.assertContains(response, "You do not need to choose or upload a file")
        self.assertContains(response, "Save resume &amp; continue")
        self.assertContains(response, "Work experience")
        self.assertContains(response, "Resume preview")
        self.assertContains(response, 'id="onboarding-career-choice-map"')
        self.assertContains(response, "Software engineering")
        self.assertContains(response, "Human resources")

        response = self.client.get(reverse("onboarding"))
        self.assertNotContains(response, "Hello, I’m Sandy, your friendly signup guide")
        self.assertContains(response, "data-sandy-question")
        self.assertContains(response, "data-question-text")

    def test_recruiter_company_lookup_prefills_and_skips_duplicate_company_question(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "shopee_recruiter",
                "email": "recruiter@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "recruiter",
                "company_name": "Shopee",
                "company_website": "https://shopee.sg/",
                "company_logo_url": "https://example.com/shopee.png",
            },
        )

        self.assertRedirects(response, reverse("onboarding"))
        response = self.client.get(reverse("onboarding"))
        self.assertContains(response, "Which industry does your company operate in?")
        self.assertNotContains(response, "What is your company called?")

        profile = UserProfile.objects.get(user__username="shopee_recruiter")
        self.assertEqual(profile.profile_data["company"], "Shopee")
        self.assertEqual(profile.profile_data["website"], "https://shopee.sg/")
        self.assertEqual(profile.user.recruiter_profile.company.logo_url, "https://example.com/shopee.png")

    def test_candidate_can_choose_guided_resume_builder(self):
        user = self._create_user("guided_candidate")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_step"] = 0
        session.save()

        response = self.client.post(reverse("onboarding"), {
            "action": "save_resume",
            "name": "Guided Candidate",
            "email": "guided@example.com",
            "phone_country_code": "+65",
            "experience_entries": '[{"position":"Intern","company":"SkillBridge","start_date":"2026-01","end_date":"","current":true,"skills":"Django","achievements":"Built matching tools"}]',
            "certification_entries": "[]",
        })

        self.assertRedirects(response, reverse("onboarding"))
        self.assertEqual(self.client.session["onboarding_step"], 1)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.profile_data["name"], "Guided Candidate")
        self.assertIn("Intern — SkillBridge", user.profile.profile_data["experience"])

    def test_resume_upload_is_scanned_and_suitable_resume_autofills_fields(self):
        user = self._create_user("resume_scan")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        resume = SimpleUploadedFile(
            "resume.txt",
            b"Alex Tan\nalex@example.com\n+65 9123 4567\n\nEducation\nBachelor of Computing, National University of Singapore, 2022\n\nExperience\nSoftware Engineer Intern, 2023\nBuilt Django services and SQL reporting tools for clients. Collaborated with developers and analysts to deliver projects.\n\nSkills\nPython, Django, SQL, Git",
            content_type="text/plain",
        )

        response = self.client.post(reverse("onboarding"), {"action": "extract_resume", "resume": resume}, follow=True)

        self.assertContains(response, 'value="Alex Tan"')
        self.assertContains(response, 'value="alex@example.com"')
        self.assertContains(response, "Python, Django, SQL, Git")
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.resume)
        self.assertEqual(user.profile.profile_data["experience_entries"][0]["skills"], "Python, Django, SQL, Git")
        self.assertIn("Built Django services", user.profile.profile_data["experience_entries"][0]["achievements"])

    def test_existing_resume_has_visible_autofill_action(self):
        user = self._create_user("existing_resume_candidate")
        profile = UserProfile.objects.create(
            user=user,
            role="candidate",
            resume=SimpleUploadedFile(
                "resume.txt",
                b"Alex Tan\nalex@example.com\n+65 9123 4567\nEducation\nBachelor of Computing, National University of Singapore, 2022\nExperience\nSoftware Engineer Intern, 2023\nBuilt Django services and SQL reporting tools for clients. Collaborated with developers and analysts to deliver production projects.\nSkills\nPython, Django, SQL, Git",
                content_type="text/plain",
            ),
        )
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_step"] = 0
        session.save()

        response = self.client.get(reverse("onboarding"))
        self.assertContains(response, "Auto-fill from current resume")
        self.assertContains(response, "guided-resume.js?v=guided-builder-2")

        response = self.client.post(reverse("onboarding"), {"action": "extract_existing_resume"})
        self.assertRedirects(response, reverse("onboarding"))
        profile.refresh_from_db()
        self.assertIn("Python", profile.profile_data["skills"])

    def test_non_resume_upload_is_rejected(self):
        user = self._create_user("bad_resume")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        upload = SimpleUploadedFile("notes.txt", b"Remember to buy milk and call home tomorrow.", content_type="text/plain")

        response = self.client.post(reverse("onboarding"), {"action": "extract_resume", "resume": upload})

        self.assertContains(response, "does not pass the resume structure check")
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.resume)

    def test_file_disguised_as_pdf_is_rejected_before_scanning(self):
        user = self._create_user("fake_pdf")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        upload = SimpleUploadedFile(
            "not-a-resume.pdf",
            b"This is ordinary text renamed to use a PDF extension.",
            content_type="application/pdf",
        )

        response = self.client.post(reverse("onboarding"), {"action": "extract_resume", "resume": upload})

        self.assertContains(response, "This file is not a valid PDF")
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.resume)

    def test_only_one_resume_can_be_uploaded_at_a_time(self):
        user = self._create_user("multiple_resumes")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        files = [
            SimpleUploadedFile("first.txt", b"first resume", content_type="text/plain"),
            SimpleUploadedFile("second.txt", b"second resume", content_type="text/plain"),
        ]

        response = self.client.post(reverse("onboarding"), {"action": "extract_resume", "resume": files})

        self.assertContains(response, "Upload only one resume at a time")
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.resume)

    def test_in_place_resume_upload_requires_delete_before_replacement(self):
        user = self._create_user("replace_resume")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        resume_text = b"Alex Tan\nalex@example.com\n+65 9123 4567\nEducation\nBachelor of Computing, NUS, 2022\nExperience\nSoftware Engineer Intern, 2023\nBuilt Python and Django services for clients and delivered reporting projects with analysts.\nSkills\nPython, Django, SQL, Git"

        response = self.client.post(reverse("scan_resume_upload"), {"resume": SimpleUploadedFile("resume.txt", resume_text, content_type="text/plain")})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        response = self.client.post(reverse("scan_resume_upload"), {"resume": SimpleUploadedFile("replacement.txt", resume_text, content_type="text/plain")})
        self.assertEqual(response.status_code, 409)
        self.assertIn("Delete the current resume", response.json()["error"])

        response = self.client.post(reverse("delete_onboarding_resume"))
        self.assertEqual(response.status_code, 200)
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.resume)

    def test_save_resume_and_continue_works_after_in_place_upload(self):
        user = self._create_user("save_after_upload")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        resume_text = b"Alex Tan\nalex@example.com\n+65 9123 4567\nEducation\nBachelor of Computing, NUS, 2022\nExperience\nSoftware Engineer Intern, 2023\nBuilt Python and Django services for clients and delivered reporting projects with analysts.\nSkills\nPython, Django, SQL, Git"
        self.client.post(reverse("scan_resume_upload"), {"resume": SimpleUploadedFile("resume.txt", resume_text, content_type="text/plain")})
        profile = UserProfile.objects.get(user=user)
        data = profile.profile_data

        response = self.client.post(reverse("onboarding"), {
            "action": "save_resume",
            "name": data["name"],
            "email": data["email"],
            "phone_country_code": "+65",
            "phone": "9123 4567",
            "career": data.get("career", ""),
            "education": data.get("education", ""),
            "institution": data.get("institution", ""),
            "skills": data.get("skills", ""),
            "experience_entries": json.dumps(data.get("experience_entries", [])),
            "certification_entries": "[]",
        })

        self.assertRedirects(response, reverse("onboarding"))
        self.assertEqual(self.client.session["onboarding_step"], 1)

    def test_article_with_resume_keywords_is_rejected(self):
        user = self._create_user("article_upload")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        article = SimpleUploadedFile(
            "career-article.txt",
            b"How Education and Experience Shape Careers\nBy Alex Writer\nwriter@example.com\nPublished 2025\n\nEducation\nUniversity education can prepare people for changing industries and new technology. This article examines how schools teach adaptable skills and why lifelong learning matters to employers.\n\nExperience\nWork experience is often discussed by managers, developers, and analysts. Organisations should create internships and projects that help young people understand professional life. The evidence suggests that practical exposure can improve confidence and career decisions.\n\nSkills\nReaders should consider communication, Python, and teamwork when planning their future.",
            content_type="text/plain",
        )

        response = self.client.post(reverse("onboarding"), {"action": "extract_resume", "resume": article})

        self.assertContains(response, "does not pass the resume structure check")
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.resume)

    def test_guided_resume_draft_autosaves(self):
        user = self._create_user("draft_candidate")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.post(reverse("autosave_resume_draft"), {
            "name": "Draft Candidate",
            "email": "draft@example.com",
            "phone_country_code": "+65",
            "phone": "9000 1234",
            "skills": "Python, Django",
            "experience_entries": "[]",
            "certification_entries": "[]",
        })

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True, "message": "Draft saved"})
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.profile_data["name"], "Draft Candidate")
        self.assertEqual(user.profile.profile_data["skills"], "Python, Django")
        self.assertEqual(user.profile.profile_data["phone"], "+65 9000 1234")

    def test_candidate_name_is_saved_from_onboarding(self):
        user = self.client.post(
            reverse("signup"),
            {
                "username": "candidate",
                "email": "candidate@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )
        self.assertEqual(user.status_code, 302)

        response = self.client.post(
            reverse("onboarding"),
            {
                "action": "save_resume",
                "name": "Alex Tan",
                "email": "candidate@example.com",
                "phone_country_code": "+65",
                "experience_entries": "[]",
                "certification_entries": "[]",
                "resume": SimpleUploadedFile("alex-resume.pdf", b"%PDF-1.4\nresume contents", content_type="application/pdf"),
            },
        )

        self.assertRedirects(response, reverse("onboarding"))
        resume_name = UserProfile.objects.get(user__username="candidate").resume.name
        self.assertIn("alex-resume", resume_name)
        self.assertTrue(resume_name.endswith(".pdf"))

        self.assertEqual(
            UserProfile.objects.get(user__username="candidate").profile_data["name"],
            "Alex Tan",
        )

    def test_candidate_can_replace_resume_from_profile(self):
        from django.contrib.auth.models import User

        user = self._create_user("profile_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"name": "Alex Tan"})
        self.client.force_login(user)

        response = self.client.post(
            reverse("candidate_profile"),
            {"resume": SimpleUploadedFile("updated-resume.pdf", b"%PDF-1.4\nupdated", content_type="application/pdf")},
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        resume_name = UserProfile.objects.get(user=user).resume.name
        self.assertIn("updated-resume", resume_name)
        self.assertTrue(resume_name.endswith(".pdf"))

    def test_candidate_can_upload_profile_photo(self):
        user = self._create_user("photo_candidate")
        profile = UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        photo = SimpleUploadedFile(
            "profile.png",
            b"\x89PNG\r\n\x1a\n" + b"profile photo",
            content_type="image/png",
        )

        response = self.client.post(reverse("candidate_profile"), {"profile_photo": photo})

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertTrue(profile.profile_photo.name.startswith("profile_photos/profile"))

    def test_existing_account_login_goes_to_dashboard(self):
        from django.contrib.auth.models import User

        user = self._create_user("existing_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={})

        response = self.client.post(
            reverse("login"),
            {"username": "existing_candidate", "password": "password"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "candidates/dashboard.html")

    def test_inbox_renders_notification_timestamp(self):
        user = self._create_user("inbox_user")
        UserProfile.objects.create(user=user, role="candidate")
        Notification.objects.create(
            recipient=user,
            title="Application update",
            body="Your application was received.",
            created_at=timezone.now(),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("inbox"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application update")
        self.assertContains(response, "Your application was received.")

    def test_free_user_can_view_pro_checkout_option(self):
        user = self._create_user("free_plan")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.get(reverse("plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SkillBridge Pro")
        self.assertContains(response, "sk_test_")

    def test_pro_plan_entitlement_is_active(self):
        user = self._create_user("pro_plan")
        profile = UserProfile.objects.create(user=user, role="candidate", plan="pro")

        self.assertTrue(profile.is_pro)

    def test_failed_stripe_payment_revokes_pro_access(self):
        user = self._create_user("past_due_user")
        profile = UserProfile.objects.create(user=user, role="candidate", plan="pro")
        payment = Payment.objects.create(
            user=user,
            provider="stripe",
            amount="9.00",
            currency="SGD",
            status="paid",
            metadata={"subscription": "sub_test"},
        )

        set_stripe_entitlement(
            payment,
            active=False,
            status="past_due",
            stripe_status="past_due",
        )

        profile.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(profile.plan, "free")
        self.assertEqual(payment.status, "past_due")
        self.assertEqual(payment.metadata["subscription_status"], "past_due")

    def test_legacy_referral_signup_does_not_grant_pro(self):
        referrer = self._create_user("referrer")
        referrer_profile = UserProfile.objects.create(user=referrer, role="candidate")

        response = self.client.post(
            f"{reverse('signup')}?ref={referrer_profile.referral_code}",
            {
                "username": "referred_friend",
                "email": "friend@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
                "referral_code": referrer_profile.referral_code,
            },
        )

        self.assertRedirects(response, reverse("onboarding"))
        self.assertFalse(Referral.objects.filter(referrer=referrer).exists())
        referrer_profile.refresh_from_db()
        referred_profile = UserProfile.objects.get(user__username="referred_friend")
        self.assertFalse(referrer_profile.is_pro)
        self.assertFalse(referred_profile.is_pro)

    @patch("accounts.referral_services.extend_stripe_subscription_trial")
    def test_legacy_referral_does_not_change_stripe_billing(self, extend_trial):
        extend_trial.return_value = {"trial_end": 1234567890}
        referrer = self._create_user("paid_referrer")
        referrer_profile = UserProfile.objects.create(user=referrer, role="candidate", plan="pro")
        Payment.objects.create(
            user=referrer,
            provider="stripe",
            amount="9.00",
            currency="SGD",
            status="paid",
            metadata={"subscription": "sub_referral_test"},
        )

        self.client.post(
            reverse("signup"),
            {
                "username": "paid_referrers_friend",
                "email": "paid-friend@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
                "referral_code": referrer_profile.referral_code,
            },
        )

        extend_trial.assert_not_called()
        self.assertFalse(Referral.objects.filter(referrer=referrer).exists())
    def test_trial_pro_can_be_cancelled_without_stripe_subscription(self):
        user = self._create_user("trial_plan")
        started_at = timezone.now()
        UserProfile.objects.create(
            user=user,
            role="candidate",
            plan="pro",
            trial_started_at=started_at,
            plan_expires_at=started_at + timedelta(days=7),
        )
        self.client.force_login(user)

        response = self.client.post(reverse("cancel_pro"))

        self.assertRedirects(response, reverse("plans"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.plan, "free")
        self.assertIsNone(profile.plan_expires_at)
        self.assertIsNotNone(profile.trial_started_at)

    def test_signup_can_skip_onboarding_and_reach_dashboard(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "skip_candidate",
                "email": "skip@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )
        self.assertRedirects(response, reverse("onboarding"))

        response = self.client.post(reverse("onboarding"), {"skip": "1"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "candidates/dashboard.html")

    def test_candidate_can_go_back_and_edit_an_onboarding_answer(self):
        user = self._create_user("back_candidate")
        profile = UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"name": "Original Name", "career_stage": "beginner"},
        )
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_step"] = 2
        session["onboarding_answers"] = {"name": "Original Name", "career_stage": "beginner"}
        session.save()

        response = self.client.post(reverse("onboarding"), {"back": "1"})
        self.assertRedirects(response, reverse("onboarding"))

        response = self.client.get(reverse("onboarding"))
        self.assertContains(response, '<option value="beginner" selected>')
        self.client.post(reverse("onboarding"), {"career_stage": "intermediate"})
        profile.refresh_from_db()
        self.assertEqual(profile.profile_data["career_stage"], "intermediate")

    def test_business_onboarding_shows_optional_cross_discipline_directions(self):
        user = self._create_user("business_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"career": "business"})
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_step"] = 2
        session["onboarding_answers"] = {"career": "business"}
        session.save()

        response = self.client.get(reverse("onboarding"))

        self.assertContains(response, "Marketing")
        self.assertContains(response, "Human resources")
        self.assertContains(response, "Real estate")
        self.assertContains(response, "Would you like to learn something cross-disciplinary?")
        self.assertContains(response, 'data-cross-disciplines')
        self.assertNotContains(response, "Yes, show cross-discipline choices")
        self.assertContains(response, "AI engineering")
        self.assertContains(response, "Machine learning")

    def test_technology_onboarding_only_shows_technology_specialisations(self):
        user = self._create_user("technology_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"career": "technology"})
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_step"] = 0
        session["onboarding_answers"] = {"career": "technology"}
        session.save()

        response = self.client.get(reverse("onboarding"))

        self.assertContains(response, '<option value="software-engineering"')
        self.assertContains(response, '<option value="ai-ml"')
        self.assertContains(response, '<option value="cybersecurity"')
        self.assertNotContains(response, '<option value="human-resources"')
        self.assertNotContains(response, '<option value="real-estate"')

    def test_protected_page_uses_project_login_url(self):
        response = self.client.get(reverse("candidate_jobs"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('candidate_jobs')}",
        )

    def test_existing_login_returns_to_requested_page(self):
        user = self._create_user("returning_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={})

        response = self.client.post(
            f"{reverse('login')}?next={reverse('candidate_jobs')}",
            {"username": "returning_candidate", "password": "password"},
        )

        self.assertRedirects(response, reverse("candidate_jobs"))

    def test_signup_skip_returns_to_requested_page(self):
        response = self.client.post(
            f"{reverse('signup')}?next=/jobs/999/",
            {
                "username": "applying_candidate",
                "email": "applying@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )
        self.assertRedirects(response, reverse("onboarding"))

        response = self.client.post(reverse("onboarding"), {"skip": "1"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/jobs/999/")
