from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path
import zipfile

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from accounts.choices import (
    CAREER_CHOICES,
    CAREER_INTERESTS_BY_AREA,
    CAREER_INTEREST_CHOICES,
    CAREER_STAGE_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    PHONE_COUNTRY_CODE_CHOICES,
    SPECIALISATION_CHOICES,
    SPECIALISATIONS_BY_AREA,
    VISA_CHOICES,
    choices_for_career,
)
from accounts.forms import validate_profile_photo


MAX_RESUME_SIZE = 5 * 1024 * 1024


def validate_resume_upload(upload):
    """Reject unsupported or disguised files before resume text extraction."""
    extension = Path(upload.name or "").suffix.casefold()
    if extension not in {".pdf", ".docx", ".txt"}:
        raise ValidationError("Upload a PDF, DOCX, or TXT resume.")
    if upload.size > MAX_RESUME_SIZE:
        raise ValidationError("Resume files must be 5 MB or smaller.")
    position = upload.tell()
    try:
        upload.seek(0)
        header = upload.read(4096)
        upload.seek(0)
        if extension == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValidationError("This file is not a valid PDF.")
        if extension == ".docx":
            if not header.startswith(b"PK"):
                raise ValidationError("This file is not a valid DOCX document.")
            try:
                with zipfile.ZipFile(upload) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise ValidationError("This file is not a valid DOCX document.")
            except (zipfile.BadZipFile, OSError):
                raise ValidationError("This file is not a valid DOCX document.")
        if extension == ".txt" and b"\x00" in header:
            raise ValidationError("This TXT file contains binary data and cannot be used as a resume.")
    finally:
        upload.seek(position)


def _format_month(value):
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%b %Y")
    except (TypeError, ValueError):
        return value


class CandidateProfileForm(forms.Form):
    """Editable version of the information collected by profile onboarding."""

    name = forms.CharField(label="Full name", required=False, max_length=200)
    profile_photo = forms.FileField(
        label="Profile photo",
        required=False,
        validators=[validate_profile_photo],
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    resume = forms.FileField(
        label="Resume",
        required=False,
        validators=[validate_resume_upload],
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.docx,.txt"}),
    )
    email = forms.EmailField(label="Email address", required=False)
    phone_country_code = forms.ChoiceField(
        label="Country code",
        required=False,
        choices=PHONE_COUNTRY_CODE_CHOICES,
        initial="+65",
    )
    phone = forms.CharField(label="Phone number", required=False, max_length=40)
    career = forms.ChoiceField(label="Career area", required=False, choices=[("", "Choose an option")] + CAREER_CHOICES)
    specialisation = forms.ChoiceField(label="Specialisation", required=False, choices=[("", "Choose an option")] + SPECIALISATION_CHOICES)
    career_stage = forms.ChoiceField(label="Current level", required=False, choices=[("", "Choose your current level")] + CAREER_STAGE_CHOICES)
    career_interests = forms.MultipleChoiceField(
        label="Skill interests",
        required=False,
        choices=CAREER_INTEREST_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Choose directions from any faculty. Your career area does not limit the tracks or certificates you can explore.",
    )
    education = forms.ChoiceField(label="Education level", required=False, choices=[("", "Choose an option")] + EDUCATION_CHOICES)
    institution = forms.ChoiceField(label="School or institution", required=False, choices=[("", "Choose an option")] + INSTITUTION_CHOICES)
    experience = forms.CharField(required=False, widget=forms.HiddenInput)
    experience_entries = forms.JSONField(required=False, widget=forms.HiddenInput)
    certifications = forms.CharField(required=False, widget=forms.HiddenInput)
    certification_entries = forms.JSONField(required=False, widget=forms.HiddenInput)
    skills = forms.CharField(
        label="Technical skills and technology stack",
        required=False,
        help_text="Separate skills with commas, rather than bullet points. For example: Python, SQL, Excel, Communication.",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    portfolio = forms.CharField(label="Project portfolio links", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    awards = forms.CharField(label="Awards and achievements", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    linkedin = forms.CharField(label="LinkedIn profile", required=False, max_length=300)
    visa = forms.ChoiceField(label="Visa / work authorisation", required=False, choices=[("", "Choose an option")] + VISA_CHOICES)

    def __init__(self, *args, **kwargs):
        from .native_entries import prepare_entries
        if args and args[0] is not None:
            args = (prepare_entries(args[0]), *args[1:])
        elif kwargs.get("data") is not None:
            kwargs["data"] = prepare_entries(kwargs["data"])
        super().__init__(*args, **kwargs)
        career_area = self.data.get("career") if self.is_bound else self.initial.get("career", "")
        # Keep skill interests cross-faculty. A technology candidate may also
        # choose healthcare, finance, or any other available direction.
        self.fields["career_interests"].choices = CAREER_INTEREST_CHOICES
        self.fields["specialisation"].choices = [("", "Choose an option")] + choices_for_career(
            SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, career_area,
        )

        # Keep an existing legacy/cross-faculty choice editable on a name-only save.
        stored_specialisation = self.initial.get("specialisation", "")
        choices = self.fields["specialisation"].choices
        if stored_specialisation and stored_specialisation not in {value for value, _ in choices}:
            self.fields["specialisation"].choices = [
                *choices,
                (stored_specialisation, dict(SPECIALISATION_CHOICES).get(stored_specialisation, stored_specialisation)),
            ]

    @property
    def entry_builders(self):
        from .native_entries import entry_builders
        return entry_builders(self)

    def clean_experience_entries(self):
        raw_entries = self.cleaned_data.get("experience_entries") or []
        if not isinstance(raw_entries, list):
            raise forms.ValidationError("Work experience entries are invalid.")

        entries = []
        fields = ("position", "company", "start_date", "end_date", "skills", "achievements")
        for raw_entry in raw_entries[:20]:
            if not isinstance(raw_entry, dict):
                continue
            entry = {field: str(raw_entry.get(field, "")).strip() for field in fields}
            entry["current"] = bool(raw_entry.get("current"))
            if not entry["current"] and entry["start_date"] and entry["end_date"] and entry["end_date"] < entry["start_date"]:
                raise forms.ValidationError("An experience end date cannot be earlier than its start date.")
            if any(entry[field] for field in fields):
                entries.append(entry)
        return entries

    def clean_certification_entries(self):
        raw_entries = self.cleaned_data.get("certification_entries") or []
        if not isinstance(raw_entries, list):
            raise forms.ValidationError("Certification entries are invalid.")

        entries = []
        fields = ("name", "issuer", "issue_date", "expiry_date", "credential_id", "skills")
        for raw_entry in raw_entries[:30]:
            if not isinstance(raw_entry, dict):
                continue
            entry = {field: str(raw_entry.get(field, "")).strip() for field in fields}
            entry["no_expiry"] = bool(raw_entry.get("no_expiry"))
            if not entry["no_expiry"] and entry["issue_date"] and entry["expiry_date"] and entry["expiry_date"] < entry["issue_date"]:
                raise forms.ValidationError("A certification expiry date cannot be earlier than its issue date.")
            if any(entry[field] for field in fields):
                entries.append(entry)
        return entries

    def clean(self):
        cleaned_data = super().clean()
        entries = cleaned_data.get("experience_entries") or []
        if entries:
            blocks = []
            for entry in entries:
                heading = " — ".join(filter(None, (entry["position"], entry["company"])))
                start_date = _format_month(entry["start_date"])
                end_date = "Present" if entry["current"] else _format_month(entry["end_date"])
                dates = " – ".join(filter(None, (start_date, end_date)))
                lines = [line for line in (heading, dates) if line]
                if entry["skills"]:
                    lines.append(f"Skills: {entry['skills']}")
                if entry["achievements"]:
                    achievements = [line.strip().lstrip("•-* ") for line in entry["achievements"].splitlines() if line.strip()]
                    lines.extend(f"• {line}" for line in achievements)
                blocks.append("\n".join(lines))
            cleaned_data["experience"] = "\n\n".join(blocks)

        certifications = cleaned_data.get("certification_entries") or []
        if certifications:
            blocks = []
            for entry in certifications:
                heading = " — ".join(filter(None, (entry["name"], entry["issuer"])))
                expiry = "No expiry" if entry["no_expiry"] else _format_month(entry["expiry_date"])
                dates = " – ".join(filter(None, (_format_month(entry["issue_date"]), expiry)))
                lines = [line for line in (heading, dates) if line]
                if entry["credential_id"]:
                    lines.append(f"Credential ID: {entry['credential_id']}")
                if entry["skills"]:
                    lines.append(f"Skills: {entry['skills']}")
                blocks.append("\n".join(lines))
            cleaned_data["certifications"] = "\n\n".join(blocks)
        return cleaned_data

    def clean_linkedin(self):
        value = self.cleaned_data.get("linkedin", "").strip()
        if not value:
            return ""
        if "://" not in value:
            value = f"https://{value}"
        try:
            URLValidator()(value)
        except ValidationError:
            raise forms.ValidationError("Enter a valid LinkedIn URL, for example linkedin.com/in/your-name.")
        hostname = (urlparse(value).hostname or "").casefold()
        if hostname not in {"linkedin.com", "www.linkedin.com"}:
            raise forms.ValidationError("Please enter a LinkedIn profile URL.")
        return value
