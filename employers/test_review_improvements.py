from io import BytesIO
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from accounts.models import UserProfile
from applications.forms import CandidateInterviewForm
from applications.models import JobApplication, ApplicationReviewEvent
from employers.models import Company, RecruiterProfile
from employers.interview_review.transcripts import sample_questions
from jobs.models import Job


class ReviewImprovementsTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(username='bulk-recruiter')
        UserProfile.objects.create(user=self.recruiter, role='recruiter')
        self.company = Company.objects.create(name='Example')
        RecruiterProfile.objects.create(user=self.recruiter, company=self.company)
        self.job = Job.objects.create(title='Engineer', company=self.company, created_by=self.recruiter, employment_type='full_time')
        self.candidate = User.objects.create_user(username='bulk-candidate')
        UserProfile.objects.create(user=self.candidate, role='candidate')
        self.application = JobApplication.objects.create(candidate=self.candidate, job=self.job)
        self.client.force_login(self.recruiter)
        self.url = reverse('recruiter_applicants') + '?select=1'

    def test_selection_is_native_and_bulk_update_records_history(self):
        self.assertContains(self.client.get(self.url), 'form="bulk-applicants"')
        response = self.client.post(self.url, {'action': 'bulk_status', 'status': 'shortlisted', 'application_ids': [self.application.pk]})
        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'shortlisted')
        self.assertEqual(ApplicationReviewEvent.objects.get().previous_status, 'submitted')
        self.assertEqual(self.candidate.notifications.count(), 1)

    def test_bulk_rejects_other_recruiters_applications_atomically(self):
        outsider = User.objects.create_user(username='outside-recruiter')
        job = Job.objects.create(title='Private', company=Company.objects.create(name='Other'), created_by=outsider)
        foreign = JobApplication.objects.create(candidate=self.candidate, job=job)
        self.client.post(self.url, {'action': 'bulk_status', 'status': 'offer', 'application_ids': [self.application.pk, foreign.pk]})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'submitted')
        self.assertFalse(ApplicationReviewEvent.objects.exists())

    def test_bulk_rejects_withdrawn_manual_interview_and_empty_selection(self):
        for status, ids in [('interview', [self.application.pk]), ('withdrawn', [self.application.pk]), ('offer', [])]:
            self.client.post(self.url, {'action': 'bulk_status', 'status': status, 'application_ids': ids})
            self.application.refresh_from_db()
            self.assertEqual(self.application.status, 'submitted')
        self.application.status = 'withdrawn'
        self.application.save()
        self.client.post(self.url, {'action': 'bulk_status', 'status': 'offer', 'application_ids': [self.application.pk]})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'withdrawn')

    def test_invalid_job_filter_does_not_crash(self):
        self.assertEqual(self.client.get(reverse('recruiter_applicants'), {'job': 'bad'}).status_code, 200)

    def test_candidate_reschedule_invalid_end_is_field_error(self):
        form = CandidateInterviewForm({'requested_start': '2026-12-01T12:00', 'requested_end': '2026-12-01T11:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('requested_end', form.errors)

    def test_sample_questions_quote_only_submitted_experience(self):
        questions = sample_questions(self.job, 'EXPERIENCE\nBuilt a Python tool to automate monthly reporting.\nEDUCATION\nPrivate School')
        self.assertTrue(any('Built a Python tool' in q for q in questions))
        self.assertFalse(any('Private School' in q for q in questions))

    def test_excel_export_is_staff_only_and_escapes_formula_names(self):
        url = reverse('administration_dashboard') + '?export=xlsx'
        self.assertEqual(self.client.get(url).status_code, 302)
        self.recruiter.is_staff = True
        self.recruiter.save()
        self.job.title = '=1+1'
        self.job.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        book = load_workbook(BytesIO(response.content))
        self.assertIn('Payments', book.sheetnames)
        self.assertEqual(book['Top Jobs']['A2'].value, '=1+1')
        self.assertEqual(book['Top Jobs']['A2'].data_type, 's')
        self.assertIn('Match denominator: registered candidates', [cell.value for cell in book['Overview']['A']])

    def test_company_analytics_counts_only_this_company_and_current_statuses(self):
        JobApplication.objects.create(candidate=self.candidate, job=Job.objects.create(
            title='Second', company=self.company, created_by=self.recruiter), status='offer')
        JobApplication.objects.create(candidate=self.candidate, job=Job.objects.create(
            title='Elsewhere', company=Company.objects.create(name='Private'), created_by=self.recruiter), status='rejected')
        response = self.client.get(self.url)
        row = next(a for a in response.context['applications'] if a.pk == self.application.pk)
        self.assertEqual(row.company_application_count, 2)
        self.assertEqual(row.company_offer_count, 1)
        self.assertEqual(row.company_active_count, 1)
        self.assertEqual(row.company_rejection_count, 0)

    def test_bulk_unchanged_status_does_not_send_duplicate_notifications(self):
        self.client.post(self.url, {'action': 'bulk_status', 'status': 'submitted', 'application_ids': [self.application.pk]})
        self.assertFalse(ApplicationReviewEvent.objects.exists())
        self.assertFalse(self.candidate.notifications.exists())

    def test_filtered_excel_contains_inclusive_member_counts(self):
        self.recruiter.is_staff = True
        self.recruiter.save()
        response = self.client.get(reverse('administration_dashboard'), {'export': 'xlsx', 'stat_role': 'candidate'})
        book = load_workbook(BytesIO(response.content))
        row = list(book['Member Categories'].values)[1]
        self.assertEqual(row[1:4], (1, 100, 1))
        self.assertEqual(row[-1], 'candidate')
