"""Conservative, explainable job-posting spam signals for staff review."""

import re
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import timedelta

from django.utils import timezone

from jobs.models import Job


def _normalise(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _job_text(job):
    return _normalise(" ".join((
        job.title, job.description, job.required_skills, job.preferred_skills,
        job.location, job.employment_type,
    )))


def recruiter_spam_alerts(now=None):
    """Return review alerts; never hide jobs or penalise recruiters automatically."""
    now = now or timezone.now()
    recent_jobs = list(
        Job.objects.filter(created_at__gte=now - timedelta(days=30))
        .select_related("created_by", "company")
        .order_by("created_by_id", "-created_at", "-pk")
    )
    by_recruiter = defaultdict(list)
    for job in recent_jobs:
        if len(by_recruiter[job.created_by_id]) < 100:
            by_recruiter[job.created_by_id].append(job)

    alerts = []
    for jobs in by_recruiter.values():
        reasons = []
        last_day = [job for job in jobs if job.created_at >= now - timedelta(hours=24)]
        if len(last_day) >= 5:
            reasons.append(f"High posting frequency: {len(last_day)} listings in 24 hours")

        duplicate_pairs = []
        texts = [(job, _job_text(job)) for job in jobs]
        for index, (left, left_text) in enumerate(texts):
            if len(left_text) < 40:
                continue
            for right, right_text in texts[index + 1:]:
                if len(right_text) < 40:
                    continue
                similarity = SequenceMatcher(None, left_text, right_text).ratio()
                if similarity >= 0.88:
                    duplicate_pairs.append((left, right, round(similarity * 100)))
                    if len(duplicate_pairs) == 3:
                        break
            if len(duplicate_pairs) == 3:
                break
        if duplicate_pairs:
            reasons.append(
                f"Repeated content: {len(duplicate_pairs)} highly similar listing pair"
                f"{'s' if len(duplicate_pairs) != 1 else ''} found"
            )

        if reasons:
            alerts.append({
                "recruiter": jobs[0].created_by,
                "company": jobs[0].company,
                "reasons": reasons,
                "recent_count": len(jobs),
                "sample_jobs": jobs[:5],
                "duplicate_pairs": duplicate_pairs,
            })
    return sorted(alerts, key=lambda alert: (-len(alert["reasons"]), -alert["recent_count"]))
