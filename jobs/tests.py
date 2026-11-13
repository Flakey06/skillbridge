from django.test import TestCase

from .forms import JobForm
from .models import Job


class JobFormTests(TestCase):
    def test_listing_uses_one_combined_skills_field(self):
        form = JobForm(data={
            "title": "Backend Developer",
            "role_type": "backend_engineer",
            "description": "Build Django services.",
            "employment_type": "full_time",
            "experience_level": "entry",
            "salary_currency": "SGD",
            "salary_period": "month",
            "status": "open",
            "required_skill_choices": ["Django", "Management"],
        })

        self.assertTrue(form.is_valid(), form.errors)
        job = form.save(commit=False)
        self.assertEqual(job.required_skills, "Django, Management")
        self.assertEqual(job.preferred_skills, "")
        self.assertNotIn("preferred_skill_choices", form.fields)
        self.assertNotIn("preferred_skills", form.fields)

    def test_editing_merges_legacy_preferred_skills_into_combined_picker(self):
        job = Job(required_skills="Django", preferred_skills="Management")
        job.pk = 1

        form = JobForm(instance=job)

        self.assertEqual(form.initial["required_skill_choices"], ["Django", "Management"])

    def test_salary_range_must_be_ordered(self):
        form = JobForm(data={"salary_min": 5000, "salary_max": 3000})

        self.assertFalse(form.is_valid())
        self.assertIn("salary_max", form.errors)

    def test_weighted_matching_inputs_must_total_one_hundred(self):
        form = JobForm(
            data={
                "title": "Product Designer",
                "description": "Design digital products.",
                "employment_type": "full_time",
                "experience_level": "entry",
                "salary_currency": "SGD",
                "salary_period": "month",
                "status": "open",
                "skill_weights": "Creativity: 60\nUI/UX: 40",
                "evidence_weights": "Projects: 40\nInternship: 50\nSelf-proclaimed skills: 10",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["skill_weights"]["Creativity"], 60)
        self.assertEqual(form.cleaned_data["evidence_weights"]["Internship"], 50)

    def test_weighted_matching_inputs_reject_invalid_totals(self):
        form = JobForm(
            data={
                "title": "Product Designer",
                "description": "Design digital products.",
                "employment_type": "full_time",
                "experience_level": "entry",
                "salary_currency": "SGD",
                "salary_period": "month",
                "status": "open",
                "skill_weights": "Creativity: 70\nUI/UX: 40",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("skill_weights", form.errors)

# Create your tests here.
