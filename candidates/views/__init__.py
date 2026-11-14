"""Stable view imports; implementations are grouped by feature."""

from .common import (
    _current_profile,
    _selected_career_interests,
    _career_interest_labels,
    _context,
    _completion_percent,
)
from .profiles import _profile_initial, profile
from .resumes import choose_resume_to_edit, resume, tailor_resume_for_interest
from .jobs import jobs, applications, saved_jobs
from .calendar import calendar
from .learning import (
    CERTIFICATE_FILE_EXTENSIONS,
    MAX_CERTIFICATE_FILE_SIZE,
    _certificate_upload_error,
    _certificate_id_error,
    _catalogue_certification,
    learning,
    verification_status,
)
from .dashboard import dashboard_context
from .withdrawals import withdraw_application

__all__ = [
    "withdraw_application",
    'CERTIFICATE_FILE_EXTENSIONS',
    'MAX_CERTIFICATE_FILE_SIZE',
    'jobs',
    'profile',
    'resume',
    'choose_resume_to_edit',
    'tailor_resume_for_interest',
    'applications',
    'calendar',
    'learning',
    'verification_status',
    'saved_jobs',
    'dashboard_context',
]
