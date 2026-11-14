"""Compare resume skill coverage and the separate text-model prediction."""
from django.utils import timezone
from .ml import predict_ai_compatibility
from resumes.services import _contains, _job_skills


def assess_resume(candidate, job, resume):
    # Restore the earlier resume comparison: direct skill coverage plus a
    # separate text-model prediction. The application assessment stays separate.
    skills = _job_skills(job)
    matched = [skill for skill in skills if _contains(resume.clean_content, skill)]
    missing = [skill for skill in skills if skill not in matched]
    score = round(len(matched) / len(skills) * 100) if skills else 0
    prediction, reason = predict_ai_compatibility(resume.clean_content,
        " ".join((job.title, job.description, job.required_skills, job.preferred_skills)), score)
    relevance = {"earned": prediction, **reason}
    breakdown = {}
    assessment = ("Strong fit" if score >= 80 else "Good foundation" if score >= 60
                  else "Developing fit" if score >= 40 else "Early-stage fit")
    return {
        "resume": resume,
        "type": "Job application" if resume.job_id else "Profile resume" if resume.title == "My resume" else "General draft",
        "version": timezone.localtime(resume.updated_at).strftime("v%Y.%m.%d-%H%M"),
        "skill_score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "relevance_score": relevance.get("earned"),
        "relevance_reason": relevance.get("reason", ""),
        "assessment": assessment,
        "breakdown": breakdown,
    }


def best_resume(assessments, job):
    """Rank by skill compatibility, then text relevance; never blend model outputs."""
    return max(assessments, key=lambda item: (
        item["skill_score"],
        item["relevance_score"] if item["relevance_score"] is not None else -1,
        item["resume"].job_id == job.pk,
        bool(item["resume"].approved_at),
        item["resume"].updated_at,
    ), default=None)
