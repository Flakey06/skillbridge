from pathlib import Path

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import SecurityQuestionAnswer


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
    email = forms.EmailField(label="Email address (optional)", required=False)
    role = forms.ChoiceField(
        label="I want to use SkillBridge as",
        choices=[("candidate", "Candidate — find jobs and build my career"), ("recruiter", "Recruiter — hire candidates")],
        widget=forms.RadioSelect,
        initial="candidate",
    )
    company_name = forms.CharField(required=False, widget=forms.HiddenInput())
    company_website = forms.URLField(required=False, widget=forms.HiddenInput())
    company_logo_url = forms.URLField(required=False, widget=forms.HiddenInput())
    security_question_1 = forms.ChoiceField(
        required=False, choices=[("", "Choose a question")] + SecurityQuestionAnswer.QUESTION_CHOICES
    )
    security_answer_1 = forms.CharField(required=False, max_length=200, widget=forms.PasswordInput(render_value=True))
    security_question_2 = forms.ChoiceField(
        required=False, choices=[("", "Choose a different question")] + SecurityQuestionAnswer.QUESTION_CHOICES
    )
    security_answer_2 = forms.CharField(required=False, max_length=200, widget=forms.PasswordInput(render_value=True))
    security_question_3 = forms.ChoiceField(
        required=False, choices=[("", "Choose a different question")] + SecurityQuestionAnswer.QUESTION_CHOICES
    )
    security_answer_3 = forms.CharField(required=False, max_length=200, widget=forms.PasswordInput(render_value=True))
    password_hint = forms.CharField(
        label="Password hint",
        required=False,
        max_length=160,
        help_text="Use a reminder only you understand. Do not write your actual password.",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password2"].label = "Re-enter Password"
        for position in range(1, 4):
            self.fields[f"security_question_{position}"].label = f"Recovery question {position}"
            self.fields[f"security_answer_{position}"].label = f"Answer {position}"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
        return user

    def clean(self):
        cleaned = super().clean()
        questions = [cleaned.get(f"security_question_{position}") for position in range(1, 4)]
        answers = [cleaned.get(f"security_answer_{position}", "").strip() for position in range(1, 4)]
        supplied = [bool(question or answer) for question, answer in zip(questions, answers)]
        if any(supplied) and not all(question and answer for question, answer in zip(questions, answers)):
            raise forms.ValidationError("Complete all three recovery questions and answers, or leave the entire section blank.")
        hint = cleaned.get("password_hint", "").strip()
        if any(supplied) and not hint:
            raise forms.ValidationError("Add a password hint when setting up recovery questions.")
        if hint and not all(question and answer for question, answer in zip(questions, answers)):
            raise forms.ValidationError("Choose and answer three recovery questions when adding a password hint.")
        password = cleaned.get("password1", "")
        if hint and password and hint.casefold() == password.casefold():
            self.add_error("password_hint", "Your hint cannot be your actual password.")
        if all(questions) and len(set(questions)) != 3:
            raise forms.ValidationError("Choose three different recovery questions.")
        if any(answer and len(SecurityQuestionAnswer.normalise_answer(answer)) < 2 for answer in answers):
            raise forms.ValidationError("Each recovery answer must contain at least two characters.")
        return cleaned

    def save_security_answers(self, user):
        SecurityQuestionAnswer.objects.filter(user=user).delete()
        for position in range(1, 4):
            question = self.cleaned_data.get(f"security_question_{position}")
            answer = self.cleaned_data.get(f"security_answer_{position}")
            if not question or not answer:
                continue
            record = SecurityQuestionAnswer(user=user, position=position, question=question)
            record.set_answer(answer)
            record.save()


class SecurityQuestionSettingsForm(forms.Form):
    current_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput,
    )
    password_hint = forms.CharField(
        label="Password hint",
        max_length=160,
        help_text="Use a reminder only you understand. Do not write your actual password.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        choices = [("", "Choose a question")] + SecurityQuestionAnswer.QUESTION_CHOICES
        existing = {record.position: record.question for record in user.security_question_answers.all()}
        for position in range(1, 4):
            self.fields[f"security_question_{position}"] = forms.ChoiceField(
                label=f"Recovery question {position}",
                choices=choices,
                initial=existing.get(position, ""),
            )
            self.fields[f"security_answer_{position}"] = forms.CharField(
                label=f"Answer {position}",
                max_length=200,
                widget=forms.PasswordInput,
            )
        self.order_fields([
            "current_password",
            "security_question_1", "security_answer_1",
            "security_question_2", "security_answer_2",
            "security_question_3", "security_answer_3",
            "password_hint",
        ])

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Your current password is incorrect.")
        return password

    def clean(self):
        cleaned = super().clean()
        questions = [cleaned.get(f"security_question_{position}") for position in range(1, 4)]
        answers = [cleaned.get(f"security_answer_{position}", "").strip() for position in range(1, 4)]
        if all(questions) and len(set(questions)) != 3:
            raise forms.ValidationError("Choose three different recovery questions.")
        if any(answer and len(SecurityQuestionAnswer.normalise_answer(answer)) < 2 for answer in answers):
            raise forms.ValidationError("Each recovery answer must contain at least two characters.")
        hint = cleaned.get("password_hint", "").strip()
        password = cleaned.get("current_password", "")
        if hint and password and hint.casefold() == password.casefold():
            self.add_error("password_hint", "Your hint cannot be your actual password.")
        return cleaned

    def save(self):
        SecurityQuestionAnswer.objects.filter(user=self.user).delete()
        for position in range(1, 4):
            record = SecurityQuestionAnswer(
                user=self.user,
                position=position,
                question=self.cleaned_data[f"security_question_{position}"],
            )
            record.set_answer(self.cleaned_data[f"security_answer_{position}"])
            record.save()
        profile = self.user.profile
        profile.password_hint = self.cleaned_data["password_hint"].strip()
        profile.save(update_fields=["password_hint"])


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
