from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserProfile
from candidates.forms import CandidateProfileForm


class NativeProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="native-candidate")
        self.profile = UserProfile.objects.create(user=self.user, role="candidate", profile_data={"name": "Original"})
        self.client.force_login(self.user)

    def test_add_and_remove_preserve_unsaved_fields_without_saving(self):
        response = self.client.post(reverse("candidate_profile"), {
            "name": "Unsaved Name", "experience_count": "1", "certification_count": "0",
            "experience-0-position": "Engineer", "experience-0-company": "Example",
            "entry_action": "experience:add",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].entry_builders[0]["rows"]), 2)
        self.assertContains(response, "Unsaved Name")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data["name"], "Original")
        response = self.client.post(reverse("candidate_profile"), {
            "experience_count": "2", "experience-0-position": "Engineer",
            "experience-1-position": "Intern", "entry_action": "experience:remove:0",
        })
        rows = response.context["form"].entry_builders[0]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["position"].value(), "Intern")

    def test_named_entries_use_existing_validated_format(self):
        form = CandidateProfileForm({
            "experience_count": "1", "certification_count": "1",
            "experience-0-position": "Engineer", "experience-0-company": "Example",
            "experience-0-start_date": "2024", "experience-0-current": "on",
            "experience-0-achievements": "Delivered a project", "certification-0-name": "Python Certificate",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["experience_entries"][0]["position"], "Engineer")
        self.assertEqual(form.cleaned_data["certification_entries"][0]["name"], "Python Certificate")

    def test_rendered_profile_has_native_controls_and_single_stylesheet(self):
        response = self.client.get(reverse("candidate_profile"))
        self.assertContains(response, "Save Profile")
        self.assertContains(response, "skillbridge/css/skillbridge.css", count=1)
        self.assertNotContains(response, "<script")
        self.assertContains(response, 'name="entry_action"')
