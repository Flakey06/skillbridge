from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from applications.models import JobApplication
from employers.models import Company
from jobs.models import Job
from .models import UserProfile


class AdministrationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='demo-staff-test', password='StaffPassword92!', is_staff=True)
        self.candidate = User.objects.create_user(username='admin-test-candidate', password='CandidatePassword92!')
        UserProfile.objects.create(user=self.candidate, role='candidate')

    def test_dashboard_requires_staff_login(self):
        url = reverse('administration_dashboard')
        self.assertRedirects(self.client.get(url), reverse('administration_login') + '?next=' + url)
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_dedicated_login_rejects_nonstaff_and_bad_passwords(self):
        for username, password in [('admin-test-candidate', 'CandidatePassword92!'), ('demo-staff-test', 'wrong')]:
            response = self.client.post(reverse('administration_login'), {'username': username, 'password': password})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_staff_signs_in_and_sees_database_statistics(self):
        recruiter = User.objects.create_user(username='admin-test-recruiter')
        UserProfile.objects.create(user=recruiter, role='recruiter', plan='pro')
        company = Company.objects.create(name='Admin Test Company')
        job = Job.objects.create(title='Statistics Role', company=company, created_by=recruiter, employment_type='full_time')
        JobApplication.objects.create(candidate=self.candidate, job=job, status='shortlisted')
        response = self.client.post(reverse('administration_login'), {'username': self.staff.username, 'password': 'StaffPassword92!'})
        self.assertRedirects(response, reverse('administration_dashboard'))
        response = self.client.get(reverse('administration_dashboard'))
        metrics = dict(response.context['metrics'])
        self.assertEqual(metrics['Candidates'], 1)
        self.assertEqual(metrics['Recruiters'], 1)
        self.assertEqual(metrics['Total Applications'], 1)
        self.assertEqual(metrics['Active Pro Accounts'], 1)
        self.assertContains(response, 'Statistics Role')
        self.assertFalse(UserProfile.objects.filter(user=self.staff).exists())
        self.assertIn('no-store', response['Cache-Control'])

    def test_inactive_staff_cannot_log_in(self):
        self.staff.is_active = False
        self.staff.save(update_fields=['is_active'])
        response = self.client.post(reverse('administration_login'), {'username': self.staff.username, 'password': 'StaffPassword92!'})
        self.assertTrue(response.context['form'].errors)

    def test_logout_is_post_only_and_returns_to_staff_login(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('administration_logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('administration_logout')), reverse('administration_login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_requested_metrics_include_history_unique_candidates_and_payments(self):
        from django.utils import timezone
        from applications.models import ApplicationReviewEvent
        from .models import Payment
        recruiter = User.objects.create_user(username='metric-recruiter')
        UserProfile.objects.create(user=recruiter, role='recruiter', profile_data={'onboarding_completed_at': timezone.now().isoformat()})
        company = Company.objects.create(name='Metric Company')
        popular = Job.objects.create(title='Popular Role', company=company, created_by=recruiter, employment_type='full_time')
        second_job = Job.objects.create(title='Other Role', company=company, created_by=recruiter, employment_type='full_time')
        application = JobApplication.objects.create(candidate=self.candidate, job=popular, status='rejected')
        ApplicationReviewEvent.objects.create(application=application, reviewer=recruiter, previous_status='shortlisted', new_status='rejected')
        JobApplication.objects.create(candidate=self.candidate, job=second_job, status='interview')
        other = User.objects.create_user(username='unmatched-candidate')
        UserProfile.objects.create(user=other, role='candidate')
        JobApplication.objects.create(candidate=other, job=popular, status='submitted')
        Payment.objects.create(user=self.candidate, provider='stripe', amount='9.00', currency='SGD', status='paid', paid_at=timezone.now())
        Payment.objects.create(user=recruiter, provider='stripe', amount='12.00', currency='USD', status='cancelled', paid_at=timezone.now())
        Payment.objects.create(user=other, provider='stripe', amount='99.00', currency='SGD', status='pending')
        self.client.force_login(self.staff)
        response = self.client.get(reverse('administration_dashboard'))
        self.assertEqual(response.context['match_statistics'], {'matched': 1, 'total': 2, 'percent': 50.0})
        self.assertEqual(response.context['most_popular_job'].pk, popular.pk)
        self.assertEqual(response.context['most_popular_job'].application_total, 2)
        onboarding = {row['label']: row for row in response.context['onboarding_statistics']}
        self.assertEqual(onboarding['Recruiters']['completed'], 1)
        self.assertEqual(onboarding['Candidates']['not_recorded'], 2)
        self.assertEqual(len(response.context['payment_records']), 2)
        self.assertContains(response, 'SGD 9.00')
        self.assertContains(response, 'USD 12.00')
        self.assertNotContains(response, 'SGD 99.00')
        self.assertContains(response, 'admin-test-candidate')

    def test_zero_candidates_and_no_applications_do_not_divide_by_zero(self):
        self.candidate.delete()
        self.client.force_login(self.staff)
        response = self.client.get(reverse('administration_dashboard'))
        self.assertEqual(response.context['match_statistics']['percent'], 0)
        self.assertIsNone(response.context['most_popular_job'])

    def test_onboarding_completion_is_persisted_once_without_losing_answers(self):
        from django.test import RequestFactory
        from .views.onboarding_helpers import _finish_onboarding
        profile = self.candidate.profile
        profile.profile_data = {'name': 'Keep this name'}
        profile.save(update_fields=['profile_data'])
        request = RequestFactory().get('/onboarding/')
        request.user = self.candidate
        request.session = {}
        _finish_onboarding(request)
        profile.refresh_from_db()
        timestamp = profile.profile_data['onboarding_completed_at']
        self.assertEqual(profile.profile_data['name'], 'Keep this name')
        _finish_onboarding(request)
        profile.refresh_from_db()
        self.assertEqual(profile.profile_data['onboarding_completed_at'], timestamp)
        self.assertTrue(request.session['onboarding_complete'])
