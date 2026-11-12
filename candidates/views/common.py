"""Shared candidate context, career interests, and profile completeness."""

from accounts.models import UserProfile
from accounts.choices import CAREER_INTEREST_CHOICES


def _current_profile(request):
    """Read the profile from the database for every request.

    The auth user can keep a cached reverse one-to-one relation. That cache
    can still contain the old profile_data after the profile form has saved a
    new career direction, which makes Skill development look stale.
    """
    return UserProfile.objects.filter(user=request.user).first()


def _selected_career_interests(data):
    """Resolve the candidate's chosen direction into roadmap keys.

    New profiles use the multi-select career directions field. Older profiles
    may only have a specialisation, so use that specific target as a fallback
    instead of leaving the roadmap empty.
    """
    raw_interests = (data or {}).get("career_interests", [])
    if isinstance(raw_interests, str):
        raw_interests = [item.strip() for item in raw_interests.split(",") if item.strip()]
    if not isinstance(raw_interests, (list, tuple)):
        return []

    if not raw_interests:
        specialisation_map = {
            "backend": "software-engineering",
            "frontend": "software-engineering",
            "software-engineering": "software-engineering",
            "computer-science": "computer-science",
            "fintech": "fintech",
            "crypto": "fintech",
            "cloud-devops": "cloud-devops",
            "ai-ml": "machine-learning",
            "ai-engineering": "ai-engineering",
            "data-analytics": "machine-learning",
            "data-science": "data-science",
            "bioinformatics": "bioinformatics",
            "biomedical-science": "biomedical-science",
            "clinical-research": "clinical-research",
            "scientific-research": "scientific-research",
            "medicine-technology": "medicine-technology",
            "business-analysis": "business-analysis",
            "product-management": "business-analysis",
            "finance-investment": "finance",
            "investment": "investment",
            "audit-accounting": "audit-accounting",
            "ux-ui": "ux-ui",
        }
        fallback = specialisation_map.get(str((data or {}).get("specialisation", "")).casefold())
        raw_interests = [fallback] if fallback else []

    known = {key: key for key, _label in CAREER_INTEREST_CHOICES}
    known.update({label.casefold(): key for key, label in CAREER_INTEREST_CHOICES})
    selected = []
    for value in raw_interests:
        normalised = " ".join(str(value).casefold().replace("_", "-").split())
        key = known.get(normalised) or known.get(normalised.replace("-", " "))
        if key and key not in selected:
            selected.append(key)
    return selected


def _career_interest_labels(interests):
    labels = dict(CAREER_INTEREST_CHOICES)
    return [labels[key] for key in interests if key in labels]


def _context(request, **extra):
    profile = _current_profile(request)
    return {
        "role": getattr(profile, "role", "candidate"),
        "has_pro": profile.is_pro if profile else False,
        **extra,
    }


def _completion_percent(profile):
    data = profile.profile_data or {}
    fields = ["name", "career", "career_stage", "specialisation", "career_interests", "education", "institution", "experience", "certifications", "skills", "portfolio", "awards", "linkedin", "visa"]
    completed = sum(bool(data.get(field)) for field in fields) + bool(profile.resume)
    return round(completed / (len(fields) + 1) * 100)
