"""Deterministic skill/evidence scoring and the existing ML score integration."""

import re

from candidates.resume_parser import KNOWN_SKILLS, extract_resume_text

from .models import JobMatch
from .ml import predict_ai_compatibility


def _normalise(value):
    return re.sub(r"\s+", " ", value.strip().casefold())


def _profile_skills(candidate):
    profile = getattr(candidate, "profile", None)
    data = getattr(profile, "profile_data", {}) or {}
    raw = data.get("skills", "")
    return {
        _normalise(skill)
        for skill in re.split(r"[,\n;|]", raw)
        if skill.strip()
    }


def _profile_data(candidate):
    profile = getattr(candidate, "profile", None)
    return (getattr(profile, "profile_data", {}) or {}) if profile else {}


def _resume_text(candidate):
    from resumes.models import TailoredResume
    if getattr(candidate, "pk", None):
        main = TailoredResume.objects.filter(candidate=candidate, is_main=True).first()
        if main:
            return _normalise(main.clean_content)
    profile = getattr(candidate, "profile", None)
    resume = getattr(profile, "resume", None) if profile else None
    if not resume:
        return ""
    try:
        with resume.open("rb") as resume_file:
            return _normalise(extract_resume_text(resume_file))
    except (OSError, ValueError):
        return ""


def _contains_skill(text, skill):
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(_normalise(skill))}(?![a-z0-9])",
            _normalise(text),
        )
    )


def _dedupe_skills(skills):
    """Keep the recruiter-provided spelling while removing duplicate skills."""
    result = []
    seen = set()
    for skill in skills:
        skill = str(skill or "").strip()
        key = _normalise(skill)
        if skill and key not in seen:
            result.append(skill)
            seen.add(key)
    return result


def _job_skill_sets(job):
    """Return explicit and job-description-derived skills for scoring.

    Recruiters should still fill in required/preferred skills. Description
    extraction is a safety net for MVP listings, not a replacement for clear
    recruiter input. When a listing has no explicit required skills, detected
    skills become required so the score is based on the actual job text.
    """
    explicit_required = _dedupe_skills(job.required_skill_list)
    explicit_preferred = _dedupe_skills(job.preferred_skill_list)
    job_text = " ".join(
        [
            job.title,
            job.description,
            job.required_skills,
            job.preferred_skills,
        ]
    )
    detected = [skill for skill in KNOWN_SKILLS if _contains_skill(job_text, skill)]

    if explicit_required:
        required = explicit_required
        preferred = _dedupe_skills(explicit_preferred + [
            skill
            for skill in detected
            if _normalise(skill) not in {
                _normalise(item) for item in required + explicit_preferred
            }
        ])
    else:
        required = _dedupe_skills(detected)
        preferred = explicit_preferred

    return required, preferred


def _assessment(score):
    if score >= 80:
        return "Strong fit"
    if score >= 60:
        return "Good foundation"
    if score >= 40:
        return "Developing fit"
    return "Early-stage fit"


def _configured_weights(values, fallback):
    """Normalise valid configured weights to a single 100-point scale."""
    import math
    cleaned = {}
    for label, weight in (values or {}).items():
        try:
            number = float(weight)
        except (TypeError, ValueError):
            continue
        if str(label).strip() and math.isfinite(number) and number > 0:
            cleaned[_normalise(label)] = number
    cleaned = cleaned or fallback
    total = sum(cleaned.values())
    return {label: weight * 100 / total for label, weight in cleaned.items()} if total else {}


def _evidence_score(data, resume_text, configured):
    weights = _configured_weights(
        configured,
        {"projects": 40.0, "internship": 50.0, "self-proclaimed skills": 10.0},
    )
    combined = " ".join([resume_text, *(str(data.get(key, "")) for key in ("experience", "portfolio", "skills", "certifications"))])
    evidence = {
        "projects": bool(re.search(r"\b(project|built|developed|implemented|portfolio)\b", combined, re.I)),
        "internship": bool(re.search(r"\b(intern|internship)\b", combined, re.I)),
        "self-proclaimed skills": bool(data.get("skills") or resume_text),
    }
    earned = sum(weight for label, weight in weights.items() if evidence.get(label, False))
    return round(earned * 0.3), {
        label: {
            "earned": round(weight * 0.3) if evidence.get(label, False) else 0,
            "max": round(weight * 0.3),
            "reason": f"{label.title()} evidence {'found' if evidence.get(label, False) else 'not found'} in your profile or resume.",
        }
        for label, weight in weights.items()
    }


def calculate_match(candidate, job, resume_text=None):
    data = _profile_data(candidate)
    candidate_skills = _profile_skills(candidate)
    resume_text = _resume_text(candidate) if resume_text is None else _normalise(resume_text)
    required_skills, preferred_skills = _job_skill_sets(job)

    # Do not imply a candidate is compatible when the recruiter has not
    # provided enough job information to compare against anything.
    if not job.skill_weights and not required_skills and not preferred_skills:
        breakdown = {
            "required_skills": {"earned": 0, "max": 0},
            "preferred_skills": {"earned": 0, "max": 0},
            "job_data_quality": {"earned": 0, "max": 0},
        }
        return 0, [], [], breakdown, "Insufficient job data"

    all_skills = _dedupe_skills(required_skills + preferred_skills + list((job.skill_weights or {}).keys()))
    skill_weights = _configured_weights(
        job.skill_weights,
        {_normalise(skill): 100 / len(all_skills) for skill in all_skills} if all_skills else {},
    )
    skill_lookup = {_normalise(skill): skill for skill in all_skills}
    matched_keys = {
        key for key in skill_lookup
        if key in candidate_skills or re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", resume_text)
    }
    skill_points = round(sum(weight for key, weight in skill_weights.items() if key in matched_keys) * 0.7)
    skill_reasons = {
        label: {
            "earned": round(weight * 0.7) if label in matched_keys else 0,
            "max": round(weight * 0.7),
            "reason": f"{skill_lookup.get(label, label.title())} {'was found' if label in matched_keys else 'is missing'} from your profile or resume.",
        }
        for label, weight in skill_weights.items()
    }
    evidence_points, evidence_reasons = _evidence_score(data, resume_text, job.evidence_weights)
    breakdown = {
        "skill_match": {"earned": skill_points, "max": 70, "reason": "Weighted recruiter skill coverage.", "details": skill_reasons},
        "evidence_match": {"earned": evidence_points, "max": 30, "reason": "Weighted evidence from projects, internships, and self-declared skills.", "details": evidence_reasons},
    }
    score = sum(component["earned"] for component in breakdown.values())
    job_text = " ".join(
        (job.title, job.description, job.required_skills, job.preferred_skills)
    )
    ai_score, ai_reason = predict_ai_compatibility(resume_text, job_text, score)
    breakdown["resume_relevance"] = {"earned": ai_score, "max": 100, **ai_reason}
    matched = sorted(skill_lookup[key] for key in matched_keys)
    missing = sorted(skill_lookup[key] for key in skill_lookup if key not in matched_keys)
    return score, matched, missing, breakdown, _assessment(score)


def get_or_update_match(candidate, job):
    score, matched, missing, breakdown, assessment = calculate_match(candidate, job)
    match, _ = JobMatch.objects.update_or_create(
        candidate=candidate,
        job=job,
        defaults={
            "score": score,
            "matched_skills": matched,
            "missing_skills": missing,
            "score_breakdown": breakdown,
            "assessment": assessment,
        },
    )
    return match


def recommend_certifications_for_gap(certifications, missing_skills):
    """Return recognised certifications that cover the missing job skills."""
    recommendations = []
    for certification in certifications:
        certification_text = _normalise(certification.skills or "")
        bridges = [
            skill
            for skill in missing_skills
            if re.search(
                rf"(?<![a-z0-9]){re.escape(_normalise(skill))}(?![a-z0-9])",
                certification_text,
            )
        ]
        if bridges:
            recommendations.append({
                "certification": certification,
                "bridges": bridges,
            })
    return sorted(
        recommendations,
        key=lambda item: (-len(item["bridges"]), item["certification"].cost, item["certification"].title),
    )
