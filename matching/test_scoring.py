from django.test import SimpleTestCase
from .services import _evidence_score


class EvidenceScoringTests(SimpleTestCase):
    def test_all_evidence_can_earn_full_thirty_points(self):
        score, details = _evidence_score({"skills": "Python", "experience": "Internship: built a project"}, "", {})
        self.assertEqual(score, 30)
        self.assertEqual(details["internship"]["earned"], 15)

    def test_recruiter_ranking_changes_evidence_points(self):
        data = {"experience": "Internship"}
        internship_first, _ = _evidence_score(data, "", {"Internship": 50, "Projects": 33.3333, "Self-proclaimed skills": 16.6667})
        projects_first, _ = _evidence_score(data, "", {"Projects": 50, "Internship": 33.3333, "Self-proclaimed skills": 16.6667})
        self.assertEqual(internship_first, 15)
        self.assertEqual(projects_first, 10)


class SeparatePredictionTests(SimpleTestCase):
    def setUp(self):
        from types import SimpleNamespace
        self.candidate = SimpleNamespace(profile=SimpleNamespace(profile_data={}, resume=None))
        self.job = SimpleNamespace(title='Developer', description='Python development',
            required_skills='Python', preferred_skills='', required_skill_list=['Python'],
            preferred_skill_list=[], skill_weights={'Python': 100}, evidence_weights={})

    def test_model_prediction_never_changes_skill_compatibility(self):
        from unittest.mock import patch
        from .services import calculate_match
        results = []
        for prediction in (0, 100, None):
            with patch('matching.services.predict_ai_compatibility', return_value=(prediction, {})):
                results.append(calculate_match(self.candidate, self.job, resume_text='Python'))
        self.assertEqual([item[0] for item in results], [results[0][0]] * 3)
        self.assertEqual([item[3]['resume_relevance']['earned'] for item in results], [0, 100, None])
        self.assertEqual(results[0][1], ['Python'])

    def test_unavailable_model_does_not_substitute_skill_score(self):
        from unittest.mock import patch
        from .ml import predict_ai_compatibility
        with patch('matching.ml._trained_model', return_value=None):
            score, details = predict_ai_compatibility('Python', 'Developer', fallback_score=90)
        self.assertIsNone(score)
        self.assertEqual(details['mode'], 'unavailable')

    def test_configured_weights_are_normalised(self):
        from unittest.mock import patch
        from .services import calculate_match
        self.job.skill_weights = {'Python': 1000}
        with patch('matching.services.predict_ai_compatibility', return_value=(0, {})):
            score, _, _, breakdown, _ = calculate_match(self.candidate, self.job, resume_text='Python')
        self.assertEqual(breakdown['skill_match']['earned'], 70)
        self.assertLessEqual(score, 100)
