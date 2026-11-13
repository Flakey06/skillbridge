from django.template.loader import render_to_string
from django.test import SimpleTestCase

from .presentation import resume_document


class ResumePresentationTests(SimpleTestCase):
    def test_name_contact_sections_and_bullets_preserve_saved_text(self):
        source = 'Jamie Tan\n\njamie@example.com\n+65 9123 4567\n\nPROFESSIONAL SUMMARY\nData analyst.\n\nEXPERIENCE\n- Built reporting tools.\n'
        document = resume_document(source, 'Fallback')
        self.assertEqual(document['name'], 'Jamie Tan')
        self.assertEqual(document['contacts'], ['jamie@example.com', '+65 9123 4567'])
        self.assertEqual(document['sections'][0]['heading'], 'Professional Summary')
        self.assertEqual(document['sections'][1]['lines'], [{'text': 'Built reporting tools.', 'bullet': True}])
        self.assertIn('- Built reporting tools.', source)

    def test_heading_first_uses_fallback_without_losing_body(self):
        document = resume_document('EDUCATION\nUniversity\n', 'Jamie')
        self.assertEqual(document['name'], 'Jamie')
        self.assertEqual(document['sections'][0]['lines'][0]['text'], 'University')

    def test_preview_escapes_saved_html(self):
        document = resume_document('Jamie\nSUMMARY\n<script>alert(1)</script>', 'Fallback')
        html = render_to_string('candidates/resume.html', {'main_resume': True, 'main_resume_document': document})
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
