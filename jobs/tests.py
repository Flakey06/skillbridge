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

    def test_new_listing_starts_with_default_evidence_order(self):
        form = JobForm()
        self.assertEqual(
            form["evidence_rank_order"].value(),
            "Projects,Internship,Self-proclaimed skills",
        )

    def test_duplicate_and_unknown_ranks_keep_all_valid_evidence_types_once(self):
        form = self.ranking_form("Internship,Internship,Unknown")
        self.assertTrue(form.is_valid(), form.errors)
        weights = form.save(commit=False).evidence_weights
        self.assertEqual(set(weights), {"Projects", "Internship", "Self-proclaimed skills"})
        self.assertAlmostEqual(sum(weights.values()), 100, places=3)
        self.assertEqual(weights["Internship"], max(weights.values()))


    def test_numeric_evidence_ranks_save_the_selected_order(self):
        data = self.ranking_form("").data.copy()
        data.pop("evidence_rank_order")
        data.update(evidence_rank_order_0="2", evidence_rank_order_1="1", evidence_rank_order_2="3")
        form = JobForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        weights = form.save(commit=False).evidence_weights
        self.assertGreater(weights["Internship"], weights["Projects"])
        self.assertGreater(weights["Projects"], weights["Self-proclaimed skills"])

    def test_numeric_evidence_ranks_reject_duplicates_missing_and_out_of_range(self):
        for ranks in ((1, 1, 3), (1, "", 3), (0, 2, 3), (1, 2, 4), (1.5, 2, 3)):
            with self.subTest(ranks=ranks):
                data = self.ranking_form("").data.copy()
                data.update({f"evidence_rank_order_{i}": rank for i, rank in enumerate(ranks)})
                form = JobForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn("evidence_rank_order", form.errors)

    def test_edit_widget_displays_saved_ranking_as_numbers(self):
        job = Job(evidence_weights={"Projects": 33.3333, "Internship": 50, "Self-proclaimed skills": 16.6667})
        job.pk = 1
        html = str(JobForm(instance=job)["evidence_rank_order"])
        self.assertIn('name="evidence_rank_order_0" value="2"', html)
        self.assertIn('name="evidence_rank_order_1" value="1"', html)
