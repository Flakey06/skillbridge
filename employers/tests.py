from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from accounts.models import UserProfile

from .forms import CompanyForm
from .models import Company, RecruiterProfile
from .services import company_matches


class CompanyWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recruiter_company", password="Password123!")
        UserProfile.objects.create(user=self.user, role="recruiter")
        RecruiterProfile.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_company_industry_is_a_choice_and_logo_falls_back_to_website(self):
        form = CompanyForm(
            data={
                "name": "Example Company",
                "industry": "technology",
                "website": "example.com",
                "linkedin_url": "linkedin.com/company/example",
                "logo_url": "",
                "description": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        company = form.save()
        self.assertEqual(company.website, "https://example.com")
        self.assertIn("google.com/s2/favicons", company.logo_url)

    def test_company_form_has_server_rendered_logo_lookup(self):
        self.assertIn("linkedin_url", CompanyForm().fields)
        self.assertNotIn("profile_photo", CompanyForm().fields)
        response = self.client.get(reverse("recruiter_company"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find Company And Logo")
        response = self.client.post(reverse("recruiter_company"), {
            "name": "Shopee", "action": "find_company",
        })
        self.assertContains(response, "Found Shopee")
        self.assertContains(response, 'value="https://shopee.sg"')
        self.assertContains(response, "google.com/s2/favicons")
        self.assertNotContains(response, "<script")

        for name, website in [("Tencent", "tencent.com"), ("NUS", "nus.edu.sg")]:
            response = self.client.post(reverse("recruiter_company"), {
                "name": name, "action": "find_company",
            })
            self.assertContains(response, website)

    @patch('employers.services._wikidata_company_matches')
    def test_unknown_company_uses_public_directory_fallback(self, wikidata):
        wikidata.return_value = [{
            'name': 'Example Global Organisation',
            'website': 'https://example.org',
            'logo_url': 'https://example.org/logo.png',
        }]
        self.assertEqual(company_matches('Example Global Organisation')[0]['website'], 'https://example.org')
        wikidata.assert_called_once()
