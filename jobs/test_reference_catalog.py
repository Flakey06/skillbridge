import csv
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.test import SimpleTestCase

from .reference_catalog import _load_catalogue, suggest_skills_for_title


class ReferenceCatalogTests(SimpleTestCase):
    def setUp(self):
        _load_catalogue.cache_clear()

    def tearDown(self):
        _load_catalogue.cache_clear()

    def test_suggests_skills_for_a_similar_title(self):
        with NamedTemporaryFile("w", suffix=".csv", delete=False) as file:
            writer = csv.writer(file)
            writer.writerow(["job_id", "category", "job_title", "job_description", "job_skill_set"])
            writer.writerow(["1", "HR", "Human Resources Generalist", "", '["Recruitment", "Employee Relations"]'])
            path = Path(file.name)
        try:
            with patch("jobs.reference_catalog._catalog_path", return_value=path):
                suggestions = suggest_skills_for_title("HR Generalist")
        finally:
            path.unlink()

        self.assertEqual(suggestions[0]["title"], "Human Resources Generalist")
        self.assertIn("Recruitment", suggestions[0]["skills"])

    def test_returns_no_suggestion_for_unrelated_title(self):
        with NamedTemporaryFile("w", suffix=".csv", delete=False) as file:
            writer = csv.writer(file)
            writer.writerow(["job_id", "category", "job_title", "job_description", "job_skill_set"])
            writer.writerow(["1", "HR", "Human Resources Generalist", "", '["Recruitment"]'])
            path = Path(file.name)
        try:
            with patch("jobs.reference_catalog._catalog_path", return_value=path):
                suggestions = suggest_skills_for_title("Marine Biologist")
        finally:
            path.unlink()

        self.assertEqual(suggestions, [])
