"""Stable view imports; implementations are grouped by feature."""

from .common import _recruiter, _context
from .listings import job_detail, _publish_listing, listings, create_listing, edit_listing, delete_listing
from .imports import job_import_template, import_listings
from .applicants import applicants, applicant_detail
from .calendar import calendar
from .company import company, company_lookup
from .dashboard import dashboard

__all__ = [
    "job_detail",
    'listings',
    'create_listing',
    'job_import_template',
    'import_listings',
    'edit_listing',
    'delete_listing',
    'applicants',
    'applicant_detail',
    'calendar',
    'company',
    'company_lookup',
    'dashboard',
]
