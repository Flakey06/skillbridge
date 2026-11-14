"""Atomic, authorised status changes from the no-JavaScript selection form."""
from django.contrib import messages
from django.db import transaction
from accounts.notification_helpers import notify
from applications.forms import ApplicationStatusForm
from applications.models import ApplicationReviewEvent


def update_selected_applicants(request, applications):
    selected = set(request.POST.getlist('application_ids'))
    if not selected or len(selected) > 200 or any(not value.isdigit() for value in selected):
        messages.error(request, 'Select between 1 and 200 applicants.')
        return
    with transaction.atomic():
        rows = list(applications.select_for_update().filter(pk__in=selected))
        if len(rows) != len(selected):
            messages.error(request, 'Selection contains an unavailable application. No statuses changed.')
            return
        changes = []
        for application in rows:
            previous = application.status
            form = ApplicationStatusForm({'status': request.POST.get('status', '')}, instance=application)
            if not form.is_valid():
                messages.error(request, 'Choose a permitted status and exclude withdrawn applications. No statuses changed.')
                return
            changes.append((application, form, previous))
        changed = 0
        for application, form, previous in changes:
            if previous == application.status:
                continue
            form.save()
            ApplicationReviewEvent.objects.create(application=application, reviewer=request.user,
                previous_status=previous, new_status=application.status, note='Bulk status update')
            notify(application.candidate, 'Application status updated',
                f'Your application for {application.job.title} is now {application.get_status_display()}.', 'application')
            changed += 1
    messages.success(request, f'{changed} application status(es) updated.')
