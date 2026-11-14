from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from django.urls import resolve, Resolver404
from accounts.models import UserProfile
from accounts.profile_display import profile_display_data
from resumes.services import build_profile_resume


class ProfileDisplayTests(SimpleTestCase):
    def test_choices_display_full_labels_without_changing_stored_or_free_text(self):
        data = {'institution': 'smu', 'education': 'undergraduate', 'career': 'technology',
                'specialisation': 'ai-ml', 'visa': 'citizen', 'name': 'james',
                'experience': 'Built myAPI using Python'}
        display = profile_display_data(data)
        self.assertEqual(display['institution'], 'Singapore Management University (SMU)')
        self.assertEqual(display['education'], 'Undergraduate degree')
        self.assertEqual(display['specialisation'], 'AI / machine learning')
        self.assertEqual(display['visa'], 'Singapore Citizen')
        self.assertEqual(display['name'], 'james')
        self.assertEqual(display['experience'], data['experience'])
        self.assertEqual(data['institution'], 'smu')
        self.assertEqual(profile_display_data({'institution': 'My custom school'})['institution'], 'My custom school')

    def test_default_admin_is_not_routed_and_custom_administration_remains(self):
        for path in ['/admin/', '/admin/login/']:
            with self.assertRaises(Resolver404):
                resolve(path)
        self.assertEqual(resolve('/administration/').url_name, 'administration_dashboard')


class ResumeChoiceLabelTests(TestCase):
    def test_generated_resume_uses_choice_labels(self):
        user = User.objects.create_user(username='display-candidate')
        UserProfile.objects.create(user=user, role='candidate', profile_data={
            'name': 'james', 'education': 'undergraduate', 'institution': 'smu',
            'career': 'technology', 'specialisation': 'ai-ml', 'visa': 'citizen'})
        content = build_profile_resume(user)
        self.assertIn('Undergraduate degree\nSingapore Management University (SMU)', content)
        self.assertIn('Technology, AI / machine learning', content)
        self.assertIn('Singapore Citizen', content)
        self.assertTrue(content.startswith('james\n'))
        self.assertEqual(user.profile.profile_data['institution'], 'smu')
