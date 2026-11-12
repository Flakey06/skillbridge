from pathlib import Path

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


PROFILE_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024


def validate_profile_photo(uploaded_file):
    if not uploaded_file:
        return uploaded_file
    if Path(uploaded_file.name).suffix.casefold() not in PROFILE_PHOTO_EXTENSIONS:
        raise forms.ValidationError("Upload a JPG, PNG, or WebP image.")
    if uploaded_file.size > MAX_PROFILE_PHOTO_SIZE:
        raise forms.ValidationError("Profile photos must be 5 MB or smaller.")
    content_type = getattr(uploaded_file, "content_type", "")
    if content_type and content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise forms.ValidationError("The uploaded file must be an image.")
    position = uploaded_file.tell()
    header = uploaded_file.read(12)
    uploaded_file.seek(position)
    is_image = (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )
    if not is_image:
        raise forms.ValidationError("The uploaded file does not contain a valid JPG, PNG, or WebP image.")
    return uploaded_file


def _normalise_choices(choices):
    """Accept Django-style (value, label) choices or a simple list of labels."""
    return list(choices or [])


class SignupForm(UserCreationForm):
    email = forms.EmailField(label="Email address")
    role = forms.ChoiceField(
        label="I want to use SkillBridge as",
        choices=[("candidate", "Candidate — find jobs and build my career"), ("recruiter", "Recruiter — hire candidates")],
        widget=forms.RadioSelect,
        initial="candidate",
    )
    company_name = forms.CharField(required=False, widget=forms.HiddenInput())
    company_website = forms.URLField(required=False, widget=forms.HiddenInput())
    company_logo_url = forms.URLField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password2"].label = "Re-enter Password"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class OnboardingForm(forms.Form):
    required_css_class = "required-field"

    def __init__(self, *args, field_name, label, field_type="text", choices=None, required=True, **kwargs):
        super().__init__(*args, **kwargs)
        field_kwargs = {"label": label, "required": required}
        if field_type == "textarea":
            self.fields[field_name] = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), **field_kwargs)
        elif field_type == "file":
            self.fields[field_name] = forms.FileField(
                widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.docx,.txt"}),
                **field_kwargs,
            )
        elif field_type == "choice":
            self.fields[field_name] = forms.ChoiceField(choices=_normalise_choices(choices), widget=forms.RadioSelect, **field_kwargs)
        elif field_type == "multi":
            self.fields[field_name] = forms.MultipleChoiceField(
                choices=_normalise_choices(choices),
                widget=forms.CheckboxSelectMultiple,
                **field_kwargs,
            )
        elif field_type == "select":
            self.fields[field_name] = forms.ChoiceField(choices=[("", "Choose an option")] + _normalise_choices(choices), **field_kwargs)
        else:
            self.fields[field_name] = forms.CharField(max_length=4000, **field_kwargs)
