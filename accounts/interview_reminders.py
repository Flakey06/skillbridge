"""Show imminent-interview reminders when a participant loads an HTML page."""
import math
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from applications.models import Interview, InterviewReminder


def queue_interview_reminders(request):
    if not request.user.is_authenticated or getattr(request, '_interview_reminders_checked', False):
        return
    request._interview_reminders_checked = True
    now = timezone.now()
    due = Interview.objects.filter(
        Q(application__candidate=request.user) | Q(created_by=request.user),
        scheduled_start__gt=now, scheduled_start__lte=now + timedelta(minutes=30),
        attendance_status='scheduled',
    ).exclude(application__status__in=['withdrawn', 'rejected', 'offer']).select_related('application__job')
    for interview in due:
        _, created = InterviewReminder.objects.get_or_create(
            interview=interview, recipient=request.user, scheduled_start=interview.scheduled_start,
        )
        if created:
            remaining = max(1, math.ceil((interview.scheduled_start - now).total_seconds() / 60))
            start = timezone.localtime(interview.scheduled_start, ZoneInfo('Asia/Singapore'))
            messages.info(request,
                f'Interview reminder: {interview.application.job.title} starts in {remaining} '
                f'minute{"s" if remaining != 1 else ""}, at {start:%H:%M} SGT. '
                'Open your calendar for the meeting link and joining details.')
