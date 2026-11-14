from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import UserProfile
from accounts.statistics_presentation import member_charts
from applications.models import Interview, JobApplication
from employers.models import Company
from jobs.models import Job


class NativeInterfaceTests(TestCase):
    def test_navigation_preference_persists_and_rejects_external_redirect(self):
        user = User.objects.create_user(username="native-navigation")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)
        response = self.client.post(reverse("toggle_navigation"), {"next": "https://example.org"})
        self.assertRedirects(response, reverse("home"))
        self.assertFalse(self.client.session["sidebar_expanded"])
        self.client.post(reverse("toggle_navigation"), {"next": reverse("candidate_profile")})
        self.assertTrue(self.client.session["sidebar_expanded"])

    def test_statistics_filter_and_category_drilldown(self):
        records = [{"role": "candidate", "category": "Technology", "joined": "2026-01-01"},
                   {"role": "candidate", "category": "Finance", "joined": "2026-02-01"},
                   {"role": "recruiter", "category": "Technology", "joined": "2026-02-02"}]
        chart = member_charts(records, {"stat_role": "candidate", "category": "Finance"})
        self.assertEqual(chart["total"], 2)
        self.assertEqual(chart["growth"][0]["day"], "2026-02-01")
        self.assertEqual(chart["growth"][0]["count"], 1)
        self.assertEqual(member_charts(records, {"from": "2026-02-01"})["total"], 2)

    def test_interview_editor_uses_owned_record_and_prefills_fields(self):
        recruiter = User.objects.create_user(username="native-recruiter")
        UserProfile.objects.create(user=recruiter, role="recruiter")
        candidate = User.objects.create_user(username="native-interview-candidate")
        UserProfile.objects.create(user=candidate, role="candidate")
        company = Company.objects.create(name="Native Company")
        job = Job.objects.create(title="Native Role", company=company, created_by=recruiter, employment_type="full_time")
        application = JobApplication.objects.create(candidate=candidate, job=job, status="interview")
        interview = Interview.objects.create(application=application, created_by=recruiter, scheduled_start=timezone.now(), candidate_notes="Private candidate note")
        self.client.force_login(candidate)
        response = self.client.get(reverse("candidate_calendar"), {"edit": interview.pk})
        self.assertContains(response, "Private candidate note")
        self.assertContains(response, 'id="interview-editor"')
        self.assertNotContains(response, "<script")
        outsider = User.objects.create_user(username="native-outsider")
        UserProfile.objects.create(user=outsider, role="candidate")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("candidate_calendar"), {"edit": interview.pk}).status_code, 404)

    def test_profile_interests_are_grouped_once_and_keep_selections(self):
        from accounts.choices import CAREER_INTEREST_CHOICES
        user = User.objects.create_user(username='grouped-interest-candidate')
        UserProfile.objects.create(user=user, role='candidate', profile_data={
            'career': 'technology', 'career_interests': ['fintech', 'marketing']})
        self.client.force_login(user)
        response = self.client.get(reverse('candidate_profile'))
        groups = response.context['interest_groups']
        values = [value for group in groups for value, _ in group['choices']]
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(set(values), {value for value, _ in CAREER_INTEREST_CHOICES})
        self.assertContains(response, 'value="fintech" checked')
        self.assertContains(response, 'value="marketing" checked')
