from types import SimpleNamespace
from django.test import SimpleTestCase
from .interview_review.ratings import compile_interview_rating


class InterviewRatingTests(SimpleTestCase):
    def test_all_saved_questions_are_equally_weighted_and_unrated_excluded(self):
        result = compile_interview_rating([
            SimpleNamespace(questions=[{'rating': 5}, {'rating': None}]),
            SimpleNamespace(questions=[{'rating': 3}, {'rating': 4}]),
        ])
        self.assertEqual(result['average'], 4)
        self.assertEqual(result['percentage'], 80)
        self.assertEqual(result['rated_count'], 3)
        self.assertEqual(result['question_count'], 4)

    def test_no_ratings_are_not_reported_as_zero(self):
        self.assertIsNone(compile_interview_rating([]))
        self.assertIsNone(compile_interview_rating([SimpleNamespace(questions=[{'rating': None}])]))
