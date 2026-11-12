from django.test import TestCase

from .forms import JobForm


class JobFormTests(TestCase):
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
