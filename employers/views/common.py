"""Shared recruiter lookup and page context."""

from ..models import Company, RecruiterProfile
from ..services import website_logo_url


def _recruiter(request):
    recruiter, _ = RecruiterProfile.objects.get_or_create(user=request.user)
    profile = getattr(request.user, "profile", None)
    data = (profile.profile_data if profile else {}) or {}
    if recruiter.company_id is None and data.get("company"):
        recruiter.company, _ = Company.objects.get_or_create(
            name=data["company"],
            defaults={
                "industry": data.get("industry", ""),
                "website": data.get("website", ""),
                "logo_url": website_logo_url(data.get("website", "")),
            },
        )
        if recruiter.company and not recruiter.company.logo_url and recruiter.company.website:
            recruiter.company.logo_url = website_logo_url(recruiter.company.website)
            recruiter.company.save(update_fields=["logo_url"])
        recruiter.save(update_fields=["company"])
    return recruiter


def _context(request, **extra):
    profile = getattr(request.user, "profile", None)
    return {
        "role": "recruiter",
        "has_pro": profile.is_pro if profile else False,
        **extra,
    }
