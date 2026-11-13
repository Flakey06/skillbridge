import re

from accounts.models import UserProfile
from candidates.resume_parser import KNOWN_SKILLS, extract_resume_text
from candidates.services import merge_completed_certifications
from matching.services import get_or_update_match
from candidates.career_paths import CAREER_FIT_PROFILES, CAREER_PATHS, _candidate_source, _skill_matches


def _normalise(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _clean_lines(value):
    return [
        re.sub(r"^[•\-*\s]+", "", line).strip()
        for line in str(value or "").splitlines()
        if line.strip() and not _is_placeholder(line)
    ]


def _dedupe(values):
    result = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        key = _normalise(value)
        if value and not _is_placeholder(value) and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _is_placeholder(value):
    return _normalise(value) in {
        "",
        "na",
        "n/a",
        "none",
        "unsure",
        "not sure",
        "not provided",
    }


def _contains(text, term):
    text = _normalise(text)
    term = _normalise(term)
    if not text or not term:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def _uploaded_resume_text(profile):
    if not profile or not profile.resume:
        return ""
    try:
        with profile.resume.open("rb") as resume_file:
            return extract_resume_text(resume_file)
    except (OSError, ValueError):
        return ""


def _job_skills(job):
    """Combine recruiter-entered skills with skills found in the full job description."""
    job_text = " ".join(
        [
            job.title,
            job.description,
            job.required_skills,
            job.preferred_skills,
        ]
    )
    skills = list(job.required_skill_list) + list(job.preferred_skill_list)
    skills.extend(skill for skill in KNOWN_SKILLS if _contains(job_text, skill))
    return _dedupe(skills)


def _candidate_skills(data, resume_text):
    profile_skills = re.split(r"[,;|\n]", str(data.get("skills", "")))
    detected_skills = [skill for skill in KNOWN_SKILLS if _contains(resume_text, skill)]
    return _dedupe(profile_skills + detected_skills)


def _relevant_evidence(data, resume_text, job_skills):
    source_lines = []
    source_lines.extend(_clean_lines(data.get("experience", "")))
    source_lines.extend(_clean_lines(data.get("portfolio", "")))
    source_lines.extend(_clean_lines(data.get("awards", "")))
    source_lines.extend(_clean_lines(resume_text))
    source_lines = _dedupe(source_lines)
    if not source_lines:
        return []
    if not job_skills:
        return source_lines[:10]
    relevant = [
        line for line in source_lines
        if any(_contains(line, skill) for skill in job_skills)
    ]
    return relevant[:10] or source_lines[:10]


def _job_description_points(job, job_skills):
    description = str(job.description or "").strip()
    if not description:
        return []
    chunks = [
        chunk.strip(" •-*\t")
        for chunk in re.split(r"\n+|(?<=[.!?])\s+", description)
        if chunk.strip()
    ]
    relevant = [
        chunk for chunk in chunks
        if any(_contains(chunk, skill) for skill in job_skills)
    ]
    return _dedupe(relevant or chunks)[:5]


def _contextualize_line(line, job):
    """Reframe generic statements around the job without adding achievements."""
    text = str(line or "").strip()
    if not text:
        return ""
    job_text = _normalise(
        " ".join((job.title, job.description, job.required_skills, job.preferred_skills))
    )
    is_data_role = any(
        _contains(job_text, term)
        for term in ("data analyst", "data analysis", "data visualisation", "data visualization", "analytics")
    )
    is_design_role = any(
        _contains(job_text, term)
        for term in ("ui/ux", "user experience", "user interface", "product design")
    )
    is_people_role = any(
        _contains(job_text, term)
        for term in ("human resources", "hr ", "recruitment", "talent acquisition")
    )
    is_business_role = any(
        _contains(job_text, term)
        for term in ("business analyst", "business analysis", "stakeholder", "requirements analysis")
    )
    generic_coding = re.match(
        r"^(?:i\s+)?(?:like|love|enjoy|prefer)\s+(?:to\s+)?(?:code|coding|programming|program)\.?$",
        text,
        flags=re.I,
    )
    if generic_coding and is_data_role:
        return "I enjoy using code to analyse and visualise data."
    if generic_coding and is_design_role:
        return "I enjoy using code to build intuitive, user-centred digital experiences."
    if generic_coding and is_business_role:
        return "I enjoy using code and structured problem-solving to support data-informed decisions."
    if generic_coding and is_people_role:
        return "I enjoy using technology and structured processes to support people-focused work."
    if generic_coding:
        return "I enjoy applying programming to solve practical problems."

    generic_interest = re.match(
        r"^(?:i\s+)?(?:like|love|enjoy|am interested in)\s+(.+)$",
        text.rstrip("."),
        flags=re.I,
    )
    if generic_interest and is_data_role and any(
        word in generic_interest.group(1).casefold() for word in ("technology", "computer science", "software")
    ):
        return "I am interested in applying technology to analyse and visualise data."
    return text


def _section(title, content):
    content = str(content or "").strip()
    if _is_placeholder(content):
        return ""
    return f"{title}\n{content}" if content else ""


def build_profile_resume(candidate):
    """Build an editable general resume from the candidate's saved profile."""
    profile = UserProfile.objects.filter(user=candidate).first()
    data = merge_completed_certifications(
        candidate,
        profile.profile_data if profile else {},
    )
    name = data.get("name") or candidate.get_full_name() or candidate.username
    contact = _dedupe([data.get("email") or candidate.email, data.get("phone"), data.get("linkedin")])
    direction = ", ".join(_dedupe([data.get("career"), data.get("specialisation")]))
    sections = [
        name,
        " | ".join(contact),
        _section("PROFESSIONAL SUMMARY", f"Career direction: {direction}." if direction else ""),
        _section("CORE SKILLS", data.get("skills")),
        _section("EDUCATION", "\n".join(_dedupe([data.get("education"), data.get("institution")]))),
        _section("EXPERIENCE", data.get("experience")),
        _section("PROJECTS & PORTFOLIO", data.get("portfolio")),
        _section("CERTIFICATIONS", data.get("certifications")),
        _section("AWARDS & ACHIEVEMENTS", data.get("awards")),
        _section("WORK AUTHORISATION", data.get("visa")),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def build_tailored_resume(candidate, job):
    """Build a truthful, job-aware resume draft from both sides of the marketplace.

    Recruiter input comes from the job title, company, description, required and
    preferred skills. Candidate input comes from profile fields and the uploaded
    resume. Writing feedback and missing skills are reviewed separately in the editor.
    """
    profile = UserProfile.objects.filter(user=candidate).first()
    data = merge_completed_certifications(
        candidate,
        profile.profile_data if profile else {},
    )
    resume_text = _uploaded_resume_text(profile)
    job_skills = _job_skills(job)
    candidate_source = " ".join(
        [
            resume_text,
            *(str(data.get(key, "")) for key in (
                "skills", "experience", "certifications", "portfolio", "awards",
                "career", "specialisation", "education",
            )),
        ]
    )
    candidate_skills = _candidate_skills(data, resume_text)
    verified_job_skills = _dedupe(
        [skill for skill in job_skills if _contains(candidate_source, skill)]
    )
    relevant_evidence = _relevant_evidence(data, resume_text, job_skills)
    focus, focus_terms = _role_focus(job)
    focus_evidence = _cover_letter_evidence(data, resume_text, job_skills, focus_terms)
    prioritised_evidence = _dedupe(focus_evidence + relevant_evidence)

    name = data.get("name") or candidate.get_full_name() or candidate.username
    contact = _dedupe([
        data.get("email") or candidate.email,
        data.get("phone"),
        data.get("linkedin"),
    ])
    focus_summary = {
        "business": "support business decisions and stakeholder needs",
        "technical": "solve technical problems and build practical solutions",
        "role-relevant": f"contribute to the {job.title} role",
    }[focus]
    summary_parts = [f"Interested in using my background to {focus_summary}."]
    if data.get("career") or data.get("specialisation"):
        summary_parts.append(
            "Background in " + ", ".join(
                value for value in (data.get("career"), data.get("specialisation")) if value
            ) + "."
        )
    if verified_job_skills:
        summary_parts.append(
            "Relevant strengths include " + ", ".join(verified_job_skills) + "."
        )
    if prioritised_evidence:
        summary_parts.append(
            "Relevant evidence from my background includes "
            + " ".join(
                _contextualize_line(line, job) for line in prioritised_evidence[:2]
            )
            + "."
        )

    all_skills = _dedupe(verified_job_skills + candidate_skills)
    experience_lines = _dedupe(
        [_contextualize_line(line, job) for line in _clean_lines(data.get("experience"))]
        + [_contextualize_line(line, job) for line in prioritised_evidence]
    )
    project_lines = _dedupe(
        [_contextualize_line(line, job) for line in _clean_lines(data.get("portfolio"))]
        + [_contextualize_line(line, job) for line in focus_evidence]
    )

    sections = [
        name,
        " | ".join(contact),
        _section("TARGET ROLE", f"{job.title} at {job.company.name}"),
        _section("PROFESSIONAL SUMMARY", " ".join(summary_parts)),
        _section("CORE SKILLS", ", ".join(all_skills)),
        _section("EDUCATION", "\n".join(_dedupe([data.get("education"), data.get("institution")])),),
        _section("EXPERIENCE", "\n".join(experience_lines)),
        _section("PROJECTS & PORTFOLIO", "\n".join(project_lines)),
        _section("CERTIFICATIONS", data.get("certifications")),
        _section("AWARDS & ACHIEVEMENTS", data.get("awards")),
        _section("WORK AUTHORISATION", data.get("visa")),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def build_interest_tailored_resume(candidate, interest, skill_evidence=None):
    """Build an interest-focused draft without claiming unsupported skills."""
    path = CAREER_PATHS.get(interest) or CAREER_FIT_PROFILES.get(interest)
    if not path:
        return ""
    profile = UserProfile.objects.filter(user=candidate).first()
    data = (profile.profile_data if profile else {}) or {}
    skill_evidence = {
        skill: evidence
        for skill, evidence in (skill_evidence or {}).items()
        if evidence.get("description", "").strip() and evidence.get("duration", "").strip()
    }
    tracked_skills = path["skills"]
    included_skills = [skill for skill in tracked_skills if skill in skill_evidence]
    evidenced_skills = [
        f"{skill} — {skill_evidence[skill]['description']} ({skill_evidence[skill]['duration']})"
        for skill in included_skills
    ]
    name = data.get("name") or candidate.get_full_name() or candidate.username
    contact = _dedupe([candidate.email, data.get("phone"), data.get("linkedin")])
    sections = [
        name,
        " | ".join(contact),
        _section("TARGET DIRECTION", path["label"]),
        _section(
            "PROFESSIONAL SUMMARY",
            f"Candidate preparing for {path['label']} roles with evidence of "
            f"{', '.join(included_skills) or 'foundational experience to develop'}.",
        ),
        _section("CORE SKILLS", "\n".join(evidenced_skills)),
        _section("EXPERIENCE", data.get("experience")),
        _section("PROJECTS & PORTFOLIO", data.get("portfolio")),
        _section("CERTIFICATIONS", data.get("certifications")),
        _section("AWARDS & ACHIEVEMENTS", data.get("awards")),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _role_focus(job):
    """Choose which evidence to foreground without inventing experience."""
    job_text = _normalise(" ".join((job.title, job.description, job.required_skills, job.preferred_skills)))
    business_terms = (
        "business", "marketing", "finance", "operations", "strategy", "sales",
        "stakeholder", "requirements", "consulting", "product", "analyst",
        "management", "economics", "accounting",
    )
    technical_terms = (
        "software", "engineer", "developer", "backend", "back-end", "frontend",
        "front-end", "data", "machine learning", "cloud", "devops", "python",
        "sql", "api", "technical", "cybersecurity", "database",
    )
    business_score = sum(_contains(job_text, term) for term in business_terms)
    technical_score = sum(_contains(job_text, term) for term in technical_terms)
    if business_score > technical_score:
        return "business", business_terms
    if technical_score > business_score:
        return "technical", technical_terms
    return "role-relevant", ()


def _cover_letter_evidence(data, resume_text, job_skills, focus_terms):
    """Return short, profile-backed evidence suitable for a cover letter."""
    labelled_lines = []
    for label, value in (
        ("project", data.get("portfolio", "")),
        ("experience", data.get("experience", "")),
        ("achievement", data.get("awards", "")),
        ("resume", resume_text),
    ):
        labelled_lines.extend((label, line) for line in _clean_lines(value))

    relevant = [
        (label, line)
        for label, line in labelled_lines
        if any(_contains(line, skill) for skill in job_skills)
    ]
    focused = [
        item
        for item in labelled_lines
        if any(_contains(item[1], term) for term in focus_terms)
    ]
    return _dedupe([line for _, line in focused + relevant])[:3]


def build_tailored_cover_letter(candidate, job):
    """Create an editable, job-specific cover letter from truthful evidence."""
    profile = UserProfile.objects.filter(user=candidate).first()
    data = (profile.profile_data if profile else {}) or {}
    resume_text = _uploaded_resume_text(profile)
    job_skills = _job_skills(job)
    match = get_or_update_match(candidate, job)
    focus, focus_terms = _role_focus(job)
    evidence = _cover_letter_evidence(data, resume_text, job_skills, focus_terms)
    display_name = data.get("name") or candidate.get_full_name() or candidate.username
    matched_skills = _dedupe(match.matched_skills)[:5]
    priorities = _job_description_points(job, job_skills)[:2]

    paragraphs = [
        f"Dear Hiring Team,\n\nI am writing to apply for the {job.title} position at {job.company.name}."
    ]
    background = ", ".join(
        value for value in (data.get("career"), data.get("specialisation")) if value
    )
    if background:
        paragraphs.append(f"My background in {background} gives me a relevant foundation for this role.")
    if priorities:
        paragraphs.append("The role particularly emphasises " + "; ".join(priorities) + ".")
    if evidence:
        focus_label = {
            "business": "business-facing projects and experience",
            "technical": "technical projects and experience",
            "role-relevant": "role-relevant projects and experience",
        }[focus]
        paragraphs.append(
            f"I would highlight my {focus_label}:\n"
            + "\n".join(f"- {line}" for line in evidence)
        )
    if matched_skills:
        paragraphs.append(
            "The skills from my current profile that align most closely with this position include "
            + ", ".join(matched_skills) + "."
        )
    paragraphs.append(
        "I would welcome the opportunity to discuss how my background can contribute to your team. "
        "Thank you for considering my application."
    )
    paragraphs.append(f"Kind regards,\n{display_name}")
    return "\n\n".join(paragraphs)
