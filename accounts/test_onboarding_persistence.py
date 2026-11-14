from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserProfile


class OnboardingPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='retained-resume', email='retained@example.com')
        UserProfile.objects.create(user=self.user, role='candidate')
        self.client.force_login(self.user)
        self.url = reverse('onboarding')
        session = self.client.session
        session['onboarding_step'] = 0
        session.save()

    def payload(self):
        return {'action': 'save_resume', 'name': 'Retained Name', 'email': 'retained@example.com',
                'phone_country_code': '+65', 'phone': '81234567', 'education': 'undergraduate',
                'institution': 'smu', 'career': 'technology', 'specialisation': 'backend',
                'experience_count': '1', 'experience-0-position': 'Developer',
                'experience-0-company': 'Sample Company', 'experience-0-start_date': '2024',
                'experience-0-current': 'on', 'experience-0-achievements': 'Built reports',
                'certification_count': '1', 'certification-0-name': 'Sample Certificate',
                'certification-0-issuer': 'Sample Issuer', 'certification-0-credential_id': 'ABC123'}

    def test_save_continue_then_back_restores_every_field_and_preview(self):
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.assertEqual(self.client.session['onboarding_step'], 1)
        self.client.post(self.url, {'back': '1'})
        response = self.client.get(self.url)
        form = response.context['resume_form']
        for key in ('name', 'phone', 'education', 'institution', 'career', 'specialisation'):
            self.assertEqual(form[key].value(), self.payload()[key])
        self.assertContains(response, 'Retained Name')
        self.assertContains(response, 'Singapore Management University (SMU)')
        self.assertContains(response, 'Sample Certificate')
        self.assertContains(response, 'Developer')

    def test_update_preview_saves_without_advancing(self):
        data = self.payload()
        data['action'] = 'save_resume_draft'
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(self.client.session['onboarding_step'], 0)
        self.assertContains(response, 'Retained Name')
        self.assertContains(response, 'Sample Certificate')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.profile_data['name'], 'Retained Name')
        self.assertNotIn('onboarding_resume_draft', self.client.session)

    def test_entry_actions_keep_unfinished_fields_across_a_reload(self):
        data = self.payload()
        data['email'] = 'unfinished'
        data['entry_action'] = 'certification:add'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotIn('name', self.user.profile.profile_data)
        response = self.client.get(self.url)
        form = response.context['resume_form']
        self.assertEqual(form['name'].value(), 'Retained Name')
        self.assertEqual(form['email'].value(), 'unfinished')
        self.assertEqual(len(form.entry_builders[1]['rows']), 2)

    def test_save_and_sign_out_persists_profile_before_logging_out(self):
        data = self.payload()
        data['action'] = 'save_resume_logout'
        self.client.post(self.url, data, follow=True)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.profile_data['name'], 'Retained Name')
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.context['resume_form']['institution'].value(), 'smu')
