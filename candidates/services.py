from .models import CandidateMilestone, CandidateProfile
from .resume_parser import autofill_profile_data, extract_resume_text


PROFILE_FIELD_MAP = {
    "career": "career_area",
    "specialisation": "specialisation",
    "education": "education_level",
    "institution": "institution",
    "certifications": "certifications",
    "linkedin": "linkedin_url",
    "experience": "work_experience",
    "portfolio": "portfolio_links",
    "awards": "awards",
    "skills": "technical_skills",
    "visa": "visa_status",
    "phone": "phone_number",
}


def add_verified_certificate_to_resume(user, milestone):
    """Add a verified certificate to the candidate's resume profile once."""
    if milestone.status != "completed":
        return False

    from accounts.models import UserProfile

    profile = UserProfile.objects.filter(user=user).first()
    if not profile:
        return False

    data = dict(profile.profile_data or {})
    entries = data.get("certification_entries", [])
    if not isinstance(entries, list):
        entries = []
    title = milestone.certification.title
    if any(isinstance(entry, dict) and entry.get("name") == title for entry in entries):
        return False

    entry = {
        "name": title,
        "issuer": milestone.certification.provider,
        "issue_date": "",
        "expiry_date": "",
        "no_expiry": False,
        "credential_id": milestone.certificate_id,
        "skills": milestone.certification.skills,
    }
    entries.append(entry)
    data["certification_entries"] = entries
    data["certifications"] = "\n".join(
        f"{item['name']} — {item['issuer']}" if item.get("issuer") else item["name"]
        for item in entries
        if item.get("name")
    )
    profile.profile_data = data
    profile.save(update_fields=["profile_data"])
    return True


def sync_candidate_profile(user, data):
    candidate_profile, _ = CandidateProfile.objects.get_or_create(user=user)
    for data_key, model_field in PROFILE_FIELD_MAP.items():
        if data_key in data:
            setattr(candidate_profile, model_field, data.get(data_key, ""))
    tracked_fields = ["resume", "name", *PROFILE_FIELD_MAP.keys()]
    completed = sum(bool(data.get(field)) for field in tracked_fields)
    candidate_profile.profile_complete_percent = round(completed / len(tracked_fields) * 100)
    candidate_profile.save()
    return candidate_profile


def merge_completed_certifications(user, data):
    """Include verified milestone certificates in every profile representation."""
    merged = dict(data or {})
    lines = [
        line.strip()
        for line in str(merged.get("certifications", "") or "").splitlines()
        if line.strip()
    ]
    seen = {line.casefold() for line in lines}
    certificates = list(merged.get("completed_career_certificates", []) or [])
    certificate_titles = {
        str(item.get("title", "")).strip().casefold()
        for item in certificates
        if isinstance(item, dict)
    }
    for milestone in CandidateMilestone.objects.filter(
        candidate=user,
        status="completed",
    ).select_related("certification"):
        title = milestone.certification.title.strip()
        if not title:
            continue
        label = title
        if milestone.certificate_id:
            label = f"{title} (Certificate ID: {milestone.certificate_id})"
        if label.casefold() not in seen:
            lines.append(label)
            seen.add(label.casefold())
        if title.casefold() not in certificate_titles:
            certificates.append(
                {
                    "title": title,
                    "provider": milestone.certification.provider,
                    "certificate_id": milestone.certificate_id,
                }
            )
            certificate_titles.add(title.casefold())
    merged["certifications"] = "\n".join(lines)
    merged["completed_career_certificates"] = certificates
    from accounts.models import UserProfile

    user_profile = UserProfile.objects.filter(user=user).first()
    if user_profile and user_profile.profile_data != merged:
        user_profile.profile_data = merged
        user_profile.save(update_fields=["profile_data"])
    candidate_profile, _ = CandidateProfile.objects.get_or_create(user=user)
    if candidate_profile.certifications != merged["certifications"]:
        candidate_profile.certifications = merged["certifications"]
        candidate_profile.save(update_fields=["certifications", "updated_at"])
    return merged


def autofill_from_resume(resume_file, existing_data):
    text = extract_resume_text(resume_file)
    if not text:
        return {}, ""
    return autofill_profile_data(text, existing_data), text
