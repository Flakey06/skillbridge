from django.test import TestCase
from types import SimpleNamespace

from .ml_model import _model_path, evaluate_model, initialise_model
from .services import calculate_match


class MlModelEvaluationTests(TestCase):
    def test_baseline_evaluation_reports_metrics_without_leakage_fields(self):
        results = evaluate_model()

        self.assertEqual(results["records"], 1000)
        self.assertGreaterEqual(results["accuracy"], 0)
        self.assertLessEqual(results["accuracy"], 1)
        self.assertIn("AI Score (0-100)", results["excluded_fields"])
        self.assertNotIn("AI Score (0-100)", results.keys())

    def test_persisted_joblib_model_can_be_loaded(self):
        model = initialise_model()

        self.assertTrue(_model_path().is_file())
        self.assertTrue(hasattr(model, "predict_proba"))

    def test_weighted_skill_match_uses_skill_and_evidence_weights(self):
        candidate = SimpleNamespace(
            profile=SimpleNamespace(
                profile_data={
                    "skills": "Creativity, UI/UX",
                    "portfolio": "Created a creativity portfolio project.",
                    "experience": "UI/UX internship",
                },
                resume=None,
            )
        )
        job = SimpleNamespace(
            title="Product Designer",
            description="",
            industry="",
            required_skills="",
            preferred_skills="",
            experience_level="entry",
            required_skill_list=[],
            preferred_skill_list=[],
            skill_weights={"Creativity": 60, "UI/UX": 40},
            evidence_weights={"Projects": 40, "Internship": 50, "Self-proclaimed skills": 10},
        )

        score, matched, missing, breakdown, _assessment = calculate_match(candidate, job)

        self.assertEqual(score, 100)
        self.assertEqual(sorted(matched), ["Creativity", "UI/UX"])
        self.assertEqual(missing, [])
        self.assertEqual(breakdown["skill_match"]["earned"], 70)
        self.assertEqual(breakdown["evidence_match"]["earned"], 30)
