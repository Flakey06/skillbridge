from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Payment, Referral, UserProfile
from .payment_services import PaymentProviderError, stripe_customer_for_user, create_stripe_checkout


class BillingSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='billing-settings', email='billing@example.com')
        self.profile = UserProfile.objects.create(user=self.user, role='candidate')
        self.client.force_login(self.user)

    def test_referral_admin_is_removed(self):
        self.assertNotIn(Referral, admin.site._registry)

    @override_settings(STRIPE_SECRET_KEY='')
    @patch('accounts.views.payments.stripe_customer_for_user')
    def test_unconfigured_stripe_explains_unavailability_without_trial_prompt(self, customer):
        response = self.client.get(reverse('account_settings'))
        self.assertNotContains(response, 'payment-demo-prompt')
        self.assertContains(response, 'Card entry is unavailable')
        response = self.client.post(reverse('manage_payment_method'))
        self.assertEqual(response.status_code, 302)
        customer.assert_not_called()

    @override_settings(STRIPE_SECRET_KEY='sk_test_example')
    @patch('accounts.views.payments.create_stripe_card_portal', return_value={'url': 'https://billing.stripe.com/p/session-example'})
    @patch('accounts.views.payments.stripe_customer_for_user', return_value='cus_own')
    def test_card_update_uses_signed_in_customer_not_posted_id(self, customer, portal):
        response = self.client.post(reverse('manage_payment_method'), {'customer': 'cus_someone_else'})
        self.assertEqual(response['Location'], 'https://billing.stripe.com/p/session-example')
        customer.assert_called_once_with(self.user)
        self.assertEqual(portal.call_args.kwargs['customer_id'], 'cus_own')
        self.assertEqual(self.client.get(reverse('manage_payment_method')).status_code, 405)

    @override_settings(STRIPE_SECRET_KEY='sk_test_example')
    @patch('accounts.views.payments.create_stripe_card_portal', side_effect=PaymentProviderError('Portal unavailable'))
    @patch('accounts.views.payments.stripe_customer_for_user', return_value='cus_own')
    def test_provider_failure_keeps_plan_and_returns_to_settings(self, customer, portal):
        response = self.client.post(reverse('manage_payment_method'))
        self.assertEqual(response['Location'], reverse('account_settings') + '#payment-method')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, 'free')

    @patch('accounts.payment_services._stripe_request', return_value={'id': 'cus_created'})
    def test_new_customer_reference_is_reused_without_card_data(self, request):
        self.assertEqual(stripe_customer_for_user(self.user), 'cus_created')
        self.assertEqual(stripe_customer_for_user(self.user), 'cus_created')
        request.assert_called_once()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_data, {'stripe_customer_id': 'cus_created'})

    @patch('accounts.payment_services._stripe_request', return_value={'url': 'https://checkout.stripe.com/example'})
    def test_checkout_reuses_card_customer(self, request):
        self.profile.profile_data = {'stripe_customer_id': 'cus_existing'}
        self.profile.save(update_fields=['profile_data'])
        create_stripe_checkout(user=self.user, payment_id=1, success_url='http://testserver/success', cancel_url='http://testserver/cancel')
        self.assertEqual(request.call_args.kwargs['data']['customer'], 'cus_existing')
        self.assertNotIn('customer_email', request.call_args.kwargs['data'])

    @patch('accounts.views.payments.cancel_stripe_subscription')
    def test_paid_plan_cancellation_remains_available_and_cancels_subscription(self, cancel):
        self.profile.plan = 'pro'
        self.profile.save(update_fields=['plan'])
        payment = Payment.objects.create(user=self.user, provider='stripe', status='paid', amount=9, metadata={'subscription': 'sub_own'})
        self.assertContains(self.client.get(reverse('plans')), 'Cancel Plan')
        self.assertEqual(self.client.get(reverse('cancel_pro')).status_code, 405)
        response = self.client.post(reverse('cancel_pro'))
        self.assertRedirects(response, reverse('plans'))
        cancel.assert_called_once_with('sub_own')
        self.profile.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.profile.plan, 'free')
        self.assertEqual(payment.status, 'cancelled')

    @override_settings(STRIPE_SECRET_KEY='')
    def test_prompt_is_only_shown_during_active_seven_day_trial(self):
        now = timezone.now()
        self.profile.plan = 'pro'
        self.profile.pro_trial_started_at = now
        self.profile.plan_expires_at = now + timedelta(days=7)
        self.profile.save()
        response = self.client.get(reverse('account_settings'))
        self.assertContains(response, 'Add Payment Details')
        self.assertContains(response, 'seven-day free trial')
        self.profile.plan_expires_at = now - timedelta(seconds=1)
        self.profile.save()
        self.assertNotContains(self.client.get(reverse('account_settings')), 'payment-demo-prompt')
        self.profile.plan_expires_at = None
        self.profile.save()
        self.assertNotContains(self.client.get(reverse('account_settings')), 'payment-demo-prompt')
