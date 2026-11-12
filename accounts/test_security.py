"""Recovery tokens, protected settings and profile synchronisation."""
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import UserProfile


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountSecurityTests(TestCase):
    def setUp(self):
        self.password = "Original-Passphrase-827!"
        self.user = User.objects.create_user(username="security-user", email="james@example.com", password=self.password)
        self.profile = UserProfile.objects.create(user=self.user, role="candidate", profile_data={"name": "James", "skills": "Python"})

    def details(self, **extra):
        return {"name": "James Updated", "email": self.user.email, "phone_country_code": "+65", "phone": "9123 4567", **extra}

    def test_recovery_links_present_on_login_and_signup(self):
        for route in ('login', 'signup'):
            self.assertContains(self.client.get(reverse(route)), reverse('password_reset'))

    def test_reset_email_and_single_use_token(self):
        response = self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        path = re.search(r'http://testserver(/password-reset/\S+)', mail.outbox[0].body).group(1)
        response = self.client.get(path, follow=True)
        self.assertTrue(response.context['validlink'])
        confirm = response.request['PATH_INFO']
        response = self.client.post(confirm, {'new_password1': 'Fresh-Passphrase-729!', 'new_password2': 'Fresh-Passphrase-729!'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Fresh-Passphrase-729!'))
        self.assertFalse(self.client.get(path, follow=True).context['validlink'])

    def test_unknown_email_has_same_confirmation_without_email(self):
        response = self.client.post(reverse('password_reset'), {'email': 'missing@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_and_expired_links_are_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(reverse('password_reset_confirm', args=[uid, 'invalid-token']))
        self.assertFalse(response.context['validlink'])
        token = default_token_generator.make_token(self.user)
        with override_settings(PASSWORD_RESET_TIMEOUT=0):
            from django.utils import timezone
            with patch.object(default_token_generator, '_now', return_value=timezone.now().replace(tzinfo=None) + timedelta(seconds=5)):
                response = self.client.get(reverse('password_reset_confirm', args=[uid, token]), follow=True)
                self.assertFalse(response.context['validlink'])

    def test_settings_require_login(self):
        self.assertEqual(self.client.get(reverse('account_settings')).status_code, 302)

    def test_details_sync_without_password_change(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post(reverse('account_settings'), self.details()), reverse('account_settings'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data['name'], 'James Updated')
        self.assertEqual(self.profile.profile_data['phone'], '+65 9123 4567')
        self.assertEqual(self.profile.profile_data['skills'], 'Python')
        self.assertEqual(self.user.candidate_profile.phone_number, '+65 9123 4567')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_email_change_requires_current_password(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('account_settings'), self.details(email='new@example.com'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['password_form'].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'james@example.com')
        self.assertRedirects(self.client.post(reverse('account_settings'), self.details(email='new@example.com', old_password=self.password)), reverse('account_settings'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data['email'], 'new@example.com')

    def test_password_change_preserves_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('account_settings'), self.details(old_password=self.password, new_password1='Fresh-Passphrase-729!', new_password2='Fresh-Passphrase-729!'))
        self.assertRedirects(response, reverse('account_settings'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Fresh-Passphrase-729!'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_invalid_password_changes_do_not_save_any_details(self):
        self.client.force_login(self.user)
        for fields in [dict(old_password='wrong', new_password1='Fresh-Passphrase-729!', new_password2='Fresh-Passphrase-729!'), dict(old_password=self.password, new_password1='Fresh-Passphrase-729!', new_password2='different'), dict(old_password=self.password, new_password1='123', new_password2='123')]:
            response = self.client.post(reverse('account_settings'), self.details(**fields))
            self.assertTrue(response.context['password_form'].errors)
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.profile_data['name'], 'James')

    def test_recruiter_settings_and_icon(self):
        self.profile.role = 'recruiter'
        self.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('recruiter_company')), reverse('account_settings'))
        self.assertRedirects(self.client.post(reverse('account_settings'), self.details()), reverse('account_settings'))
        self.assertFalse(hasattr(self.user, 'candidate_profile'))
