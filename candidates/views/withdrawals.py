"""Candidate-owned withdrawal of an existing application."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import candidate_required
from accounts.notification_helpers import notify
from applications.models import JobApplication


@candidate_required
@require_POST
def withdraw_application(request, application_id):
    application = get_object_or_404(
        JobApplication.objects.select_related('job'), pk=application_id, candidate=request.user,
    )
    if application.status in {'rejected', 'offer'}:
        return HttpResponseForbidden('Rejected applications and offers cannot be withdrawn.')
    changed = JobApplication.objects.filter(pk=application.pk).exclude(status__in=['withdrawn', 'rejected', 'offer']).update(
        status='withdrawn', updated_at=timezone.now(),
    )
    if changed:
        notify(application.job.created_by, 'Application withdrawn',
               f'{request.user.username} withdrew their application for {application.job.title}.', 'application')
        messages.success(request, 'Your application has been withdrawn.')
    if request.POST.get('return_to') == 'job':
        return redirect(reverse('job_detail', args=[application.job_id]) + '#job-application-title')
    return redirect(reverse('candidate_applications') + f'#application-{application.pk}')
