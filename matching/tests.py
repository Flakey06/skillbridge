from django.test import TestCase
from types import SimpleNamespace

from .services import calculate_match


class SkillEvidenceTests(TestCase):
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


class RidgePredictionTests(TestCase):
    def test_active_model_is_ridge_and_returns_a_bounded_prediction(self):
        from sklearn.linear_model import Ridge
        from sklearn.feature_extraction.text import TfidfVectorizer
        from .ml import DATASET_PATH, _trained_model, predict_ai_compatibility
        pipeline, rows = _trained_model(DATASET_PATH.stat().st_mtime_ns)
        self.assertIsInstance(pipeline.steps[0][1], TfidfVectorizer)
        self.assertIsInstance(pipeline.steps[-1][1], Ridge)
        self.assertGreaterEqual(rows, 10)
        score, metadata = predict_ai_compatibility('Python SQL reporting project', 'Data analyst using SQL and Python')
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertEqual(metadata['mode'], 'dataset')
