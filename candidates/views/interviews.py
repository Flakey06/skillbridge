"""Candidate access to an accepted in-app video interview."""

from urllib.parse import urlparse
from uuid import uuid4

from django.shortcuts import get_object_or_404, render

from accounts.decorators import candidate_required
from applications.models import Interview

from .common import _context


@candidate_required
def interview_room(request, interview_id):
    interview = get_object_or_404(
        Interview.objects.select_related("application__job__company"),
        pk=interview_id,
        application__candidate=request.user,
        response_status="accepted",
        contact_method="video",
    )
    meeting_host = (urlparse(interview.meeting_url).hostname or "").casefold()
    if not interview.meeting_url or meeting_host not in {"meet.jit.si", "www.meet.jit.si"}:
        interview.meeting_url = f"https://meet.jit.si/skillbridge-{uuid4().hex}"
        interview.save(update_fields=["meeting_url"])
    return render(request, "candidates/interview_room.html", _context(
        request,
        interview=interview,
        application=interview.application,
    ))
