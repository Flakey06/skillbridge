from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from applications.forms import ApplicationStatusForm
from applications.models import JobApplication, Interview
from employers.models import Company
from jobs.models import Job


class InterviewSchedulingRulesTests(TestCase):
    def setUp(self):
        recruiter = User.objects.create_user(username='interview-rule-recruiter')
        self.recruiter = recruiter
        UserProfile.objects.create(user=recruiter, role='recruiter')
        candidate = User.objects.create_user(username='interview-rule-candidate', email='candidate@example.com')
        self.candidate = candidate
        UserProfile.objects.create(user=candidate, role='candidate', profile_data={'phone': '+65 8123 4567', 'linkedin': 'https://www.linkedin.com/in/candidate'})
        company = Company.objects.create(name='Interview Company')
        job = Job.objects.create(title='Role', company=company, created_by=recruiter, employment_type='full_time')
        self.application = JobApplication.objects.create(candidate=candidate, job=job)
        self.client.force_login(recruiter)

    def test_schedule_button_requires_saved_shortlisted_status(self):
        url = reverse('recruiter_applicant_detail', args=[self.application.pk])
        for status in ['submitted', 'shortlisted', 'interview', 'offer', 'rejected', 'withdrawn']:
            self.application.status = status
            self.application.save(update_fields=['status'])
            response = self.client.get(url)
            if status == 'shortlisted':
                self.assertContains(response, f'?application={self.application.pk}')
            else:
                self.assertNotContains(response, 'applicant-schedule-interview')

    def test_interview_is_not_a_manual_status_choice(self):
        for status in ['submitted', 'interview']:
            self.application.status = status
            form = ApplicationStatusForm(instance=self.application)
            self.assertNotIn('interview', dict(form.fields['status'].choices))
            self.assertFalse(ApplicationStatusForm({'status': 'interview'}, instance=self.application).is_valid())

    def test_scheduling_shortlisted_application_sets_interview_automatically(self):
        self.application.status = 'shortlisted'
        self.application.save(update_fields=['status'])
        response = self.client.get(reverse('recruiter_calendar'), {'application': self.application.pk})
        self.assertEqual(response.context['selected_application'].pk, self.application.pk)
        self.assertContains(response, 'Calendar downloads sync it to the timezone configured')
        self.assertContains(response, 'Interview start')
        response = self.client.post(reverse('recruiter_calendar'), {
            'application_id': self.application.pk, 'scheduled_start': '2026-12-01T14:00',
        })
        self.assertRedirects(response, reverse('recruiter_calendar'))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'interview')
        self.assertEqual(self.application.get_status_display(), 'Interview')
        self.assertEqual(Interview.objects.filter(application=self.application).count(), 1)

    def test_candidate_can_accept_scheduled_interview(self):
        self.application.status = 'interview'
        self.application.save(update_fields=['status'])
        interview = Interview.objects.create(
            application=self.application,
            created_by=self.recruiter,
            scheduled_start='2026-12-01T14:00:00+08:00',
            scheduled_end='2026-12-01T15:00:00+08:00',
        )
        self.client.force_login(self.candidate)

        response = self.client.post(reverse('candidate_calendar'), {
            'interview_id': interview.pk,
            'action': 'accept',
        })

        self.assertRedirects(response, reverse('candidate_calendar'))
        interview.refresh_from_db()
        self.assertEqual(interview.response_status, 'accepted')

    def test_candidate_reschedule_rejects_candidate_or_recruiter_conflict(self):
        self.application.status = 'interview'
        self.application.save(update_fields=['status'])
        interview = Interview.objects.create(
            application=self.application,
            created_by=self.recruiter,
            scheduled_start='2026-12-01T14:00:00+08:00',
            scheduled_end='2026-12-01T15:00:00+08:00',
        )
        other_candidate = User.objects.create_user(username='other-interview-candidate')
        other_application = JobApplication.objects.create(
            candidate=other_candidate,
            job=self.application.job,
            status='interview',
        )
        Interview.objects.create(
            application=other_application,
            created_by=self.recruiter,
            scheduled_start='2026-12-02T14:00:00+08:00',
            scheduled_end='2026-12-02T15:00:00+08:00',
        )
        self.client.force_login(self.candidate)

        response = self.client.post(reverse('candidate_calendar'), {
            'interview_id': interview.pk,
            'requested_start': '2026-12-02T14:30',
            'requested_end': '2026-12-02T15:30',
            'reschedule_reason': 'Need another time',
            'candidate_notes': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'conflicts with another candidate or recruiter interview')
        interview.refresh_from_db()
        self.assertNotEqual(interview.reschedule_status, 'pending')
        self.assertIsNone(interview.proposed_start)

    def test_cannot_schedule_non_shortlisted_application_via_direct_post(self):
        response = self.client.post(reverse('recruiter_calendar'), {
            'application_id': self.application.pk, 'scheduled_start': '2026-12-01T14:00',
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Interview.objects.filter(application=self.application).exists())

    def test_status_save_returns_to_progress_section(self):
        url = reverse('recruiter_applicant_detail', args=[self.application.pk])
        response = self.client.post(url, {'status': 'shortlisted'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('recruiter_calendar') + f'?application={self.application.pk}')
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'shortlisted')
        response = self.client.get(url)
        self.assertContains(response, 'id="update-progress"')

    def test_recruiter_sees_candidate_contact_methods(self):
        response = self.client.get(reverse('recruiter_applicant_detail', args=[self.application.pk]))
        self.assertContains(response, 'mailto:candidate@example.com')
        self.assertContains(response, 'tel:+65 8123 4567')
        self.assertContains(response, 'https://www.linkedin.com/in/candidate')

    def test_interview_records_contact_method(self):
        self.application.status = 'shortlisted'
        self.application.save(update_fields=['status'])
        self.client.post(reverse('recruiter_calendar'), {
            'application_id': self.application.pk,
            'scheduled_start': '2026-12-01T14:00',
            'contact_method': 'phone',
            'contact_details': '+65 8123 4567',
        })
        interview = Interview.objects.get(application=self.application)
        self.assertEqual(interview.contact_method, 'phone')
        self.assertEqual(interview.contact_details, '+65 8123 4567')

    def test_video_interview_uses_transcription_workspace_without_built_in_call(self):
        self.application.status = 'shortlisted'
        self.application.save(update_fields=['status'])
        self.client.post(reverse('recruiter_calendar'), {
            'application_id': self.application.pk,
            'scheduled_start': '2026-12-01T14:00',
            'contact_method': 'video',
        })
        interview = Interview.objects.get(application=self.application)
        self.assertEqual(interview.meeting_url, '')

        interview.response_status = 'accepted'
        interview.save(update_fields=['response_status'])

        calendar_page = self.client.get(reverse('recruiter_calendar'))
        workspace_url = reverse('recruiter_interview_workspace', args=[interview.pk])
        self.assertContains(calendar_page, workspace_url)
        workspace = self.client.get(workspace_url)
        self.assertContains(workspace, 'Start transcription')
        self.assertContains(workspace, 'Generate summary')
        self.assertContains(workspace, 'Private recruiter notes')
        self.assertNotContains(workspace, '<iframe')
        self.assertNotContains(workspace, 'Jitsi')

    def test_recruiter_can_generate_and_save_summary_from_transcript_and_notes(self):
        self.application.status = 'interview'
        self.application.save(update_fields=['status'])
        interview = Interview.objects.create(
            application=self.application,
            created_by=self.recruiter,
            scheduled_start='2026-12-01T14:00:00+08:00',
            scheduled_end='2026-12-01T15:00:00+08:00',
            response_status='accepted',
        )
        workspace_url = reverse('recruiter_interview_workspace', args=[interview.pk])
        response = self.client.post(workspace_url, {
            'action': 'generate_summary',
            'transcript': 'Jamie described a Django project. Jamie explained the deployment process.',
            'notes': 'Strong, specific technical examples.',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('Django project', response.json()['summary'])
        self.assertIn('Recruiter notes:', response.json()['summary'])
        interview.refresh_from_db()
        self.assertEqual(interview.summary, response.json()['summary'])
        self.assertIn('deployment process', interview.transcript)

    def test_candidate_interview_clash_requires_confirmation(self):
        other_job = Job.objects.create(
            title='Other interview role', company=self.application.job.company,
            created_by=self.application.job.created_by, employment_type='full_time',
        )
        other_application = JobApplication.objects.create(
            candidate=self.application.candidate, job=other_job, status='interview',
        )
        Interview.objects.create(
            application=other_application,
            created_by=self.application.job.created_by,
            scheduled_start='2026-12-01T14:00:00+08:00',
            scheduled_end='2026-12-01T15:00:00+08:00',
        )
        self.application.status = 'shortlisted'
        self.application.save(update_fields=['status'])
        url = reverse('recruiter_calendar')
        data = {
            'application_id': self.application.pk,
            'scheduled_start': '2026-12-01T14:30',
            'scheduled_end': '2026-12-01T15:30',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Potential interview clash')
        self.assertEqual(Interview.objects.filter(application=self.application).count(), 0)
        response = self.client.post(url, {**data, 'confirm_conflict': 'yes'})
        self.assertRedirects(response, url)
        self.assertEqual(Interview.objects.filter(application=self.application).count(), 1)
