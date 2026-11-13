from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company
from jobs.models import Job
from resumes.models import TailoredResume


class ResumeTimelineDisplayTests(TestCase):
    def test_timeline_marks_selected_main_and_limits_entries_to_owner(self):
        user = User.objects.create_user(username='timeline-candidate')
        UserProfile.objects.create(user=user, role='candidate')
        other = User.objects.create_user(username='other-timeline-candidate')
        company = Company.objects.create(name='Timeline Company')
        job = Job.objects.create(title='Timeline Engineer', company=company, created_by=other, employment_type='full_time')
        current = TailoredResume.objects.create(candidate=user, job=job, title='Selected Version', is_main=True)
        for index in range(4):
            TailoredResume.objects.create(candidate=user, job=job, title=f'Other version {index}')
        TailoredResume.objects.create(candidate=other, title='Private version')
        self.client.force_login(user)
        response = self.client.get(reverse('candidate_resume'))
        self.assertEqual([len(row) for row in response.context['resume_timeline_rows']], [4, 1])
        self.assertEqual(response.context['resume_timeline'][-1]['resume'].pk, current.pk)
        self.assertContains(response, 'aria-current="true"', count=1)
        self.assertContains(response, 'resume-timeline-current', count=1)
        self.assertContains(response, 'Timeline Engineer')
        self.assertContains(response, 'Timeline Company')
        self.assertContains(response, reverse('resume_detail', args=[current.pk]))
        self.assertNotContains(response, 'Private version')

    def test_empty_timeline_has_helpful_message(self):
        user = User.objects.create_user(username='empty-timeline-candidate')
        UserProfile.objects.create(user=user, role='candidate')
        self.client.force_login(user)
        response = self.client.get(reverse('candidate_resume'))
        self.assertContains(response, 'Your first dated version will appear')
