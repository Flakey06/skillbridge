"""Shared interview overlap checks for recruiters and candidates."""

from datetime import timedelta

from django.utils import timezone

from .models import Interview


def scheduling_conflicts(application, recruiter, start, end=None, *, exclude_interview=None):
    """Return other candidate/recruiter interviews overlapping the proposed slot."""
    proposed_end = end or start + timedelta(hours=1)
    candidate_interviews = Interview.objects.filter(
        application__candidate=application.candidate,
    ).select_related("application__job", "application__candidate", "created_by")
    recruiter_interviews = Interview.objects.filter(
        created_by=recruiter,
    ).select_related("application__candidate", "application__job")
    if exclude_interview:
        candidate_interviews = candidate_interviews.exclude(pk=exclude_interview.pk)
        recruiter_interviews = recruiter_interviews.exclude(pk=exclude_interview.pk)

    conflicts = []
    seen = set()
    for kind, existing in [
        *(("Candidate", item) for item in candidate_interviews),
        *(("Recruiter", item) for item in recruiter_interviews),
    ]:
        existing_end = existing.scheduled_end or existing.scheduled_start + timedelta(hours=1)
        if existing.scheduled_start < proposed_end and existing_end > start and existing.pk not in seen:
            seen.add(existing.pk)
            conflicts.append({
                "kind": kind,
                "title": existing.application.job.title,
                "candidate": existing.application.candidate.username,
                "start": timezone.localtime(existing.scheduled_start),
                "end": timezone.localtime(existing_end),
            })
    return conflicts
