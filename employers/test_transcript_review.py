from datetime import timedelta
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import UserProfile
from applications.models import Interview, InterviewReview, JobApplication
from jobs.models import Job
from employers.models import Company
from employers.interview_review.transcripts import parse_turns, suggest_answers

TRANSCRIPT = '''1
00:00:05.120 --> 00:00:09.430
Alex Johnson: How did you use Python to automate reporting?

2
00:00:10.050 --> 00:00:14.220
Sarah Chen: I built a Python script to produce weekly reports.
It saved two hours each week.
'''


class TranscriptMatchingTests(SimpleTestCase):
    def test_timestamped_multiline_answer_and_speaker_identification(self):
        turns = parse_turns(TRANSCRIPT)
        self.assertEqual(len(turns), 2)
        rows = suggest_answers([{'question': 'How did you use Python to automate reporting?'}], turns, 'Sarah Chen')
        self.assertIn('saved two hours', rows[0]['answer'])
        self.assertIn('Alex', turns[0]['speaker'])
        self.assertNotIn('-->', rows[0]['answer'])

    def test_unrelated_question_is_left_blank_and_manual_edits_survive(self):
        rows = suggest_answers([{'question': 'Explain database replication failures'},
            {'question': 'Python reporting', 'answer': 'Recruiter correction'}], parse_turns(TRANSCRIPT), 'Sarah Chen')
        self.assertFalse(rows[0].get('answer'))
        self.assertEqual(rows[1]['answer'], 'Recruiter correction')


class InterviewReviewWorkflowTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(username='review-recruiter')
        UserProfile.objects.create(user=self.recruiter, role='recruiter')
        self.candidate = User.objects.create_user(username='review-candidate')
        company = Company.objects.create(name='Review Company')
        self.job = Job.objects.create(title='Python Engineer', company=company, created_by=self.recruiter,
            employment_type='full_time', required_skills='Python')
        application = JobApplication.objects.create(candidate=self.candidate, job=self.job)
        self.interview = Interview.objects.create(application=application, created_by=self.recruiter,
            scheduled_start=timezone.now() - timedelta(days=1))
        self.url = reverse('recruiter_interview_review', args=[self.interview.pk])
        self.client.force_login(self.recruiter)

    def payload(self, action):
        return {'action': action, 'transcript': TRANSCRIPT, 'candidate_speaker': 'Sarah Chen',
            'summary': '', 'overall_notes': 'Relevant example', 'questions-TOTAL_FORMS': '1',
            'questions-INITIAL_FORMS': '0', 'questions-MIN_NUM_FORMS': '0', 'questions-MAX_NUM_FORMS': '30',
            'questions-0-question': 'How did you use Python to automate reporting?',
            'questions-0-answer': '', 'questions-0-rating': '4'}

    def test_preview_matches_without_saving_and_save_persists_review(self):
        response = self.client.post(self.url, self.payload('analyse'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'I built a Python script')
        self.assertFalse(InterviewReview.objects.exists())
        data = self.payload('save')
        data['questions-0-answer'] = 'Checked answer'
        data['summary'] = 'Checked summary'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        review = InterviewReview.objects.get(interview=self.interview)
        self.assertEqual(review.questions[0]['rating'], 4)
        self.assertEqual(review.questions[0]['answer'], 'Checked answer')
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.summary, 'Checked summary')
        self.assertEqual(self.interview.application.status, 'submitted')
        self.assertContains(self.client.get(self.url), 'Checked answer')

    def test_upload_lists_speakers_and_add_question_retains_answers(self):
        data = self.payload('load')
        data['candidate_speaker'] = ''
        data['transcript_file'] = SimpleUploadedFile('meeting.txt', TRANSCRIPT.encode())
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Sarah Chen')
        data = self.payload('add_question')
        data['questions-0-answer'] = 'Keep this edit'
        response = self.client.post(self.url, data)
        self.assertEqual(len(response.context['question_formset'].forms), 2)
        self.assertContains(response, 'Keep this edit')

    def test_other_recruiter_is_blocked_and_future_interview_can_be_prepared(self):
        other = User.objects.create_user(username='other-reviewer')
        UserProfile.objects.create(user=other, role='recruiter')
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload('save')).status_code, 404)
        self.client.force_login(self.recruiter)
        self.interview.scheduled_start = timezone.now() + timedelta(days=1)
        self.interview.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_invalid_file_and_rating_do_not_save(self):
        data = self.payload('save')
        data['transcript_file'] = SimpleUploadedFile('meeting.pdf', b'not text')
        data['questions-0-rating'] = '9'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertTrue(response.context['question_formset'].errors)
        self.assertFalse(InterviewReview.objects.exists())

    def test_notes_become_questions_and_remain_saved_with_submitted_resume(self):
        self.interview.application.tailored_resume = 'Submitted snapshot — Python developer'
        self.interview.application.save()
        data = self.payload('notes_to_questions')
        data['loose_notes'] = 'Explain a reporting failure\nHow did you test the fix?'
        response = self.client.post(self.url, data)
        self.assertEqual(len(response.context['question_formset'].forms), 3)
        self.assertContains(response, 'Submitted snapshot — Python developer')
        self.assertFalse(InterviewReview.objects.exists())
        data = self.payload('save')
        data['loose_notes'] = 'Working thought for follow-up'
        self.client.post(self.url, data)
        self.assertEqual(InterviewReview.objects.get(interview=self.interview).loose_notes,
                         'Working thought for follow-up')
        self.assertContains(self.client.get(self.url), 'Working thought for follow-up')

    def test_interviews_list_is_owned_and_links_to_workspace(self):
        url = reverse('recruiter_interviews')
        response = self.client.get(url)
        self.assertContains(response, self.url)
        other = User.objects.create_user(username='list-other-reviewer')
        UserProfile.objects.create(user=other, role='recruiter')
        self.client.force_login(other)
        self.assertNotContains(self.client.get(url), 'Python Engineer')

    def test_bin_removes_question_immediately_and_preserves_other_fields(self):
        data = self.payload('save')
        data['questions-TOTAL_FORMS'] = '2'
        data['questions-1-question'] = 'Keep this question'
        data['questions-1-answer'] = 'Keep this answer'
        data['questions-1-rating'] = '3'
        data['remove_question'] = '0'
        data['loose_notes'] = 'Keep live notes'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        saved = InterviewReview.objects.get(interview=self.interview)
        self.assertEqual(len(saved.questions), 1)
        self.assertEqual(saved.questions[0]['question'], 'Keep this question')
        self.assertEqual(saved.questions[0]['answer'], 'Keep this answer')
        self.assertEqual(saved.loose_notes, 'Keep live notes')

    def test_sample_transcript_generates_problem_answer_summary(self):
        data = self.payload('analyse')
        data['questions-0-question'] = 'Describe a difficult problem you solved. What was your contribution and the result?'
        data['transcript'] = """1
00:01:13.000 --> 00:01:22.000
Alex Johnson: Describe a difficult problem you solved. What was your contribution and the result?

2
00:01:23.000 --> 00:01:45.000
Sarah Chen: I compared revenue files and found cancelled orders in one total. The totals then matched.
"""
        response = self.client.post(self.url, data)
        summary = response.context['form']['summary'].value()
        self.assertIn('cancelled orders', summary)
        self.assertIn('The totals then matched.', summary)
        self.assertEqual(response.context['form']['overall_notes'].value(), 'Relevant example')

    def test_upload_then_match_preserves_text_and_fills_answer_widget(self):
        data = self.payload('load')
        data['transcript'] = ''
        data['candidate_speaker'] = ''
        data['transcript_file'] = SimpleUploadedFile('meeting.txt', TRANSCRIPT.encode())
        loaded = self.client.post(self.url, data)
        retained = loaded.context['form']['transcript'].value()
        self.assertEqual(retained, TRANSCRIPT)
        self.assertContains(loaded, 'Transcript loaded: 2 speaker turns')
        # Submit the retained text, with no second upload, just as the next HTML form does.
        data = self.payload('analyse')
        data['transcript'] = retained
        matched = self.client.post(self.url, data)
        question = matched.context['question_formset'].forms[0]
        self.assertIn('I built a Python script', question['answer'].value())
        self.assertNotIn('How did you use', question['answer'].value())
        self.assertIn('I built a Python script', matched.context['form']['summary'].value())

    def test_selecting_interviewer_does_not_load_questions_as_answers(self):
        data = self.payload('analyse')
        data['candidate_speaker'] = 'Alex Johnson'
        response = self.client.post(self.url, data)
        question = response.context['question_formset'].forms[0]
        self.assertFalse(question['answer'].value())
        self.assertContains(response, 'No answers could be matched.')

    def test_stage_switch_saves_live_answers_without_overwriting_transcript_review(self):
        data = self.payload('stage_after')
        data['stage'] = 'during'
        data['questions-0-live_answer'] = 'My quick interview notes'
        data['questions-0-answer'] = 'Previously checked transcript answer'
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url + '?stage=after')
        saved = InterviewReview.objects.get(interview=self.interview)
        self.assertEqual(saved.questions[0]['live_answer'], 'My quick interview notes')
        self.assertEqual(saved.questions[0]['answer'], 'Previously checked transcript answer')
        after = self.client.get(self.url, {'stage': 'after'})
        self.assertContains(after, 'Your Interview Notes')
        self.assertContains(after, 'My quick interview notes')
        self.assertContains(after, 'Previously checked transcript answer')
        during = self.client.get(self.url)
        self.assertNotContains(during, 'Load Transcript')
        self.assertContains(during, 'Save Interview Notes')

    def test_matching_keeps_live_answer_and_adds_transcript_answer_separately(self):
        data = self.payload('analyse')
        data['stage'] = 'after'
        data['questions-0-live_answer'] = 'Mentioned Python script; verify time savings'
        response = self.client.post(self.url, data)
        question = response.context['question_formset'].forms[0]
        self.assertEqual(question['live_answer'].value(), 'Mentioned Python script; verify time savings')
        self.assertIn('saved two hours', question['answer'].value())
        self.assertEqual(response.context['stage'], 'after')

    def test_unlinked_transcript_question_can_be_added_for_review(self):
        data = self.payload('analyse')
        data['stage'] = 'after'
        data['questions-0-question'] = 'Explain database replication failures'
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Needs review: no transcript answer matched.')
        self.assertEqual(len(response.context['additional_questions']), 1)
        data['add_transcript_question'] = '0'
        response = self.client.post(self.url, data)
        forms = response.context['question_formset'].forms
        self.assertEqual(len(forms), 2)
        self.assertIn('I built a Python script', forms[1]['answer'].value())
        self.assertFalse(forms[1]['live_answer'].value())

    def test_transcript_question_without_detected_answer_is_flagged(self):
        data = self.payload('analyse')
        data['stage'] = 'after'
        data['transcript'] += '\n3\n00:01:00.000 --> 00:01:05.000\nAlex Johnson: How would you validate a new requirement?\n'
        response = self.client.post(self.url, data)
        self.assertContains(response, 'How would you validate a new requirement?')
        self.assertContains(response, 'No following candidate answer detected')
