"""Keep generated reference material out of candidate resume content."""

import re

REFERENCE_HEADINGS = {
    "EMPLOYER DETAILS USED", "JOB DESCRIPTION PRIORITIES",
    "TAILORING NOTES — REVIEW BEFORE SUBMITTING",
    "TAILORING NOTES – REVIEW BEFORE SUBMITTING",
    "TAILORING NOTES - REVIEW BEFORE SUBMITTING",
}
RESUME_HEADINGS = {
    "TARGET ROLE", "TARGET DIRECTION", "PROFESSIONAL SUMMARY", "SUMMARY",
    "PROFESSIONAL PROFILE", "CORE SKILLS", "SKILLS", "EDUCATION", "EXPERIENCE",
    "WORK EXPERIENCE", "PROJECTS", "PROJECTS & PORTFOLIO", "CERTIFICATIONS",
    "AWARDS & ACHIEVEMENTS", "AWARDS", "WORK AUTHORISATION",
}


def clean_resume_content(content):
    result = []
    skipping = False
    for line in (content or "").splitlines():
        heading = line.strip().upper().rstrip(":")
        if heading in REFERENCE_HEADINGS:
            skipping = True
            continue
        if heading in RESUME_HEADINGS:
            skipping = False
        if not skipping:
            result.append(line)
    text = "\n".join(result).replace(
        "Review every statement against the original resume before submitting.", "",
    )
    return text.strip()


def auto_format_resume(content):
    """Apply consistent plain-text resume formatting without changing claims."""
    cleaned = clean_resume_content(content).replace("\r\n", "\n").replace("\r", "\n")
    formatted = []
    previous_blank = False
    for raw_line in cleaned.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if formatted and not previous_blank:
                formatted.append("")
            previous_blank = True
            continue

        heading = line.upper().rstrip(":")
        if heading in RESUME_HEADINGS:
            if formatted and formatted[-1] != "":
                formatted.append("")
            formatted.append(heading)
            previous_blank = False
            continue

        bullet = re.match(r"^(?:[-*•▪◦]+|\d+[.)])\s*(.+)$", line)
        if bullet:
            line = f"- {bullet.group(1).strip()}"
        formatted.append(line)
        previous_blank = False

    while formatted and formatted[-1] == "":
        formatted.pop()
    return "\n".join(formatted)
