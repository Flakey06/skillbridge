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

    def ranking_form(self, order):
        return JobForm(data={
            "title": "Product Designer", "role_type": "other",
            "description": "Design digital products.", "employment_type": "full_time",
            "experience_level": "entry", "salary_currency": "SGD",
            "salary_period": "month", "status": "open", "evidence_rank_order": order,
        })

    def test_evidence_ranking_calculates_normalised_weights(self):
        form = self.ranking_form("Internship,Projects,Self-proclaimed skills")
        self.assertTrue(form.is_valid(), form.errors)
        weights = form.save(commit=False).evidence_weights
        self.assertAlmostEqual(sum(weights.values()), 100, places=3)
        self.assertGreater(weights["Internship"], weights["Projects"])
        self.assertGreater(weights["Projects"], weights["Self-proclaimed skills"])

    def test_duplicate_and_unknown_ranks_keep_all_valid_evidence_types_once(self):
        form = self.ranking_form("Internship,Internship,Unknown")
        self.assertTrue(form.is_valid(), form.errors)
        weights = form.save(commit=False).evidence_weights
        self.assertEqual(set(weights), {"Projects", "Internship", "Self-proclaimed skills"})
        self.assertAlmostEqual(sum(weights.values()), 100, places=3)
        self.assertEqual(weights["Internship"], max(weights.values()))
