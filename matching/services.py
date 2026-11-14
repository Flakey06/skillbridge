"""Explainable resume-to-job scoring for the MVP.

The score is deliberately deterministic so candidates and recruiters can see
why it changed. A TensorFlow model can replace the component calculators later
without changing the views or stored match shape.
"""

import re

from candidates.resume_parser import KNOWN_SKILLS, extract_resume_text

from .models import JobMatch
from .ml import predict_ai_compatibility


SKILL_MATCH_WEIGHT = 0.70
ML_SUITABILITY_WEIGHT = 0.30


def calculate_overall_suitability(skill_match_score, ml_suitability_score):
    """Blend direct job alignment with the historical ML signal."""
    if skill_match_score is None or ml_suitability_score is None:
        return None
    blended_score = (
        (float(skill_match_score) * SKILL_MATCH_WEIGHT)
        + (float(ml_suitability_score) * ML_SUITABILITY_WEIGHT)
    )
    return int(blended_score + 0.5)


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
    profile = getattr(candidate, "profile", None)
    resume = getattr(profile, "resume", None) if profile else None
    if not resume:
        return ""
    try:
        with resume.open("rb") as resume_file:
            return _normalise(extract_resume_text(resume_file))
    except (OSError, ValueError):
        return ""


def _coverage(profile_skills, skill_names, resume_text=""):
    normalised = {_normalise(skill): skill for skill in skill_names}
    matched_keys = {
        key
        for key in normalised
        if key in profile_skills
        or re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", resume_text)
    }
    return normalised, matched_keys


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


def _experience_points(data, job):
    raw = " ".join(str(data.get(key, "")) for key in ("experience", "certifications", "education")).casefold()
    level = job.experience_level
    if level == "entry":
        return 10 if not raw or any(word in raw for word in ("intern", "student", "entry", "graduate")) else 8
    if level == "junior":
        return 10 if any(word in raw for word in ("junior", "intern", "1 year", "2 years", "associate")) else 5
    if level == "mid":
        return 10 if any(word in raw for word in ("mid", "3 years", "4 years", "5 years")) else 4
    return 10 if any(word in raw for word in ("senior", "lead", "manager", "6 years", "7 years", "8 years")) else 3


def _alignment_points(data, job):
    job_text = _normalise(" ".join((job.industry, job.title, job.description)))
    profile_terms = [data.get("career", ""), data.get("specialisation", "")]
    return 10 if any(_normalise(term).replace("-", " ") in job_text for term in profile_terms if term) else 0


def _evidence_points(candidate, data):
    evidence = [
        data.get("skills"),
        data.get("experience"),
        data.get("certifications"),
        data.get("portfolio"),
        _resume_text(candidate),
    ]
    return round(5 * sum(bool(item) for item in evidence) / len(evidence))


def _weighted_skill_match(candidate, data, job, resume_text):
    skill_weights = job.skill_weights or {}
    if not skill_weights:
        return None
    evidence_weights = job.evidence_weights or {
        "Projects": 40,
        "Internship": 50,
        "Self-proclaimed skills": 10,
    }
    profile_skills = _profile_skills(candidate)
    evidence_text = {
        "projects": _normalise(" ".join((data.get("portfolio", ""), resume_text))),
        "internship": _normalise(" ".join((data.get("experience", ""), resume_text))),
        "self-proclaimed skills": _normalise(data.get("skills", "")),
    }
    aliases = {
        "project": "projects",
        "projects": "projects",
        "internship": "internship",
        "internships": "internship",
        "work experience": "internship",
        "experience": "internship",
        "self-proclaimed skills": "self-proclaimed skills",
        "self proclaimed skills": "self-proclaimed skills",
        "profile skills": "self-proclaimed skills",
    }
    normalised_evidence_weights = {
        aliases.get(_normalise(source), _normalise(source)): float(weight)
        for source, weight in evidence_weights.items()
    }
    total_evidence_weight = sum(normalised_evidence_weights.values()) or 100
    details = []
    weighted_score = 0
    matched = []
    missing = []
    for skill, raw_weight in skill_weights.items():
        skill_weight = float(raw_weight)
        skill_key = _normalise(skill)
        source_scores = {}
        for source, source_weight in normalised_evidence_weights.items():
            text = evidence_text.get(source, "")
            present = (
                skill_key in profile_skills
                if source == "self-proclaimed skills"
                else _contains_skill(text, skill)
            )
            source_scores[source] = {
                "matched": present,
                "weight": source_weight,
            }
        evidence_score = sum(
            item["weight"] for item in source_scores.values() if item["matched"]
        ) / total_evidence_weight
        weighted_score += skill_weight * evidence_score
        if evidence_score:
            matched.append(skill)
        else:
            missing.append(skill)
        details.append({
            "skill": skill,
            "skill_weight": skill_weight,
            "evidence_score": round(evidence_score * 100),
            "sources": source_scores,
        })
    return {
        "score": round(weighted_score),
        "matched": matched,
        "missing": missing,
        "details": details,
        "evidence_weights": normalised_evidence_weights,
    }


def _assessment(score):
    if score >= 80:
        return "Strong fit"
    if score >= 60:
        return "Good foundation"
    if score >= 40:
        return "Developing fit"
    return "Early-stage fit"


def _configured_weights(values, fallback):
    cleaned = {
        _normalise(label): float(weight)
        for label, weight in (values or {}).items()
        if str(label).strip() and float(weight) >= 0
    }
    return cleaned or fallback


def _evidence_score(data, resume_text, configured):
    weights = _configured_weights(
        configured,
        {"projects": 40.0, "internship": 50.0, "self-proclaimed skills": 10.0},
    )
    combined = " ".join(str(data.get(key, "")) for key in ("experience", "portfolio", "skills", "certifications"))
    evidence = {
        "projects": bool(re.search(r"\b(project|built|developed|implemented|portfolio)\b", combined, re.I)),
        "internship": bool(re.search(r"\b(intern|internship)\b", combined, re.I)),
        "self-proclaimed skills": bool(data.get("skills") or resume_text),
    }
    total_weight = sum(weights.values()) or 100
    earned = sum(weight for label, weight in weights.items() if evidence.get(label, False))
    return round(earned * 100 / total_weight), {
        label: {
            "earned": round(weight * 100 / total_weight) if evidence.get(label, False) else 0,
            "max": round(weight * 100 / total_weight),
            "reason": f"{label.title()} evidence {'found' if evidence.get(label, False) else 'not found'} in your profile or resume.",
        }
        for label, weight in weights.items()
    }


def calculate_match(candidate, job):
    data = _profile_data(candidate)
    candidate_skills = _profile_skills(candidate)
    resume_text = _resume_text(candidate)
    required_skills, preferred_skills = _job_skill_sets(job)
    weighted_skill_match = _weighted_skill_match(candidate, data, job, resume_text)

    # Do not imply a candidate is compatible when the recruiter has not
    # provided enough job information to compare against anything.
    if not weighted_skill_match and not required_skills and not preferred_skills:
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
    total_skill_weight = sum(skill_weights.values()) or 100
    skill_points = round(
        sum(weight for key, weight in skill_weights.items() if key in matched_keys)
        * 100 / total_skill_weight
    )
    skill_reasons = {
        label: {
            "earned": round(weight * 100 / total_skill_weight) if label in matched_keys else 0,
            "max": round(weight * 100 / total_skill_weight),
            "reason": f"{skill_lookup.get(label, label.title())} {'was found' if label in matched_keys else 'is missing'} from your profile or resume.",
        }
        for label, weight in skill_weights.items()
    }
    evidence_points, evidence_reasons = _evidence_score(data, resume_text, job.evidence_weights)
    breakdown = {
        "skill_match": {"earned": skill_points, "max": 100, "reason": "Requested skills found in the profile or submitted resume.", "details": skill_reasons},
        "evidence_match": {"earned": evidence_points, "max": 100, "reason": "Independent evidence strength from projects, internships, and self-declared skills.", "details": evidence_reasons},
    }
    # JobMatch.score is the skill-compatibility percentage. Evidence remains a
    # separate score in evidence_match and is never added to skill coverage.
    score = skill_points
    job_text = " ".join(
        (job.title, job.description, job.required_skills, job.preferred_skills)
    )
    ai_score, ai_reason = predict_ai_compatibility(resume_text, job_text, score)
    breakdown["ai_match"] = {"earned": ai_score, "max": 100, **ai_reason}
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
