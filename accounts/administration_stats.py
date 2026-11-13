"""Defined metrics used by the staff statistics dashboard."""

from django.db.models import Q

from applications.models import JobApplication


ONBOARDING_COMPLETED_KEY = 'onboarding_completed_at'


def onboarding_statistics(profiles):
    rows = []
    for role, label in [('candidate', 'Candidates'), ('recruiter', 'Recruiters')]:
        role_profiles = [profile for profile in profiles if profile.role == role]
        completed = sum(bool((profile.profile_data or {}).get(ONBOARDING_COMPLETED_KEY)) for profile in role_profiles)
        total = len(role_profiles)
        rows.append({'label': label, 'total': total, 'completed': completed,
                     'not_recorded': total - completed,
                     'percent': round(completed / total * 100, 1) if total else 0})
    return rows


def successful_match_statistics(profiles):
    candidates = profiles.filter(role='candidate')
    progressed = ['shortlisted', 'interview', 'offer']
    successful = JobApplication.objects.filter(
        Q(status__in=progressed)
        | Q(review_history__new_status__in=progressed)
        | Q(review_history__previous_status__in=progressed)
        | Q(interviews__isnull=False)
    ).values('candidate_id')
    total = candidates.count()
    matched = candidates.filter(user_id__in=successful).count()
    return {'matched': matched, 'total': total,
            'percent': round(matched / total * 100, 1) if total else 0}
