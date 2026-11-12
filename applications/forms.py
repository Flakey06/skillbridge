from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .models import Interview, JobApplication


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ["cover_note"]
        widgets = {"cover_note": forms.Textarea(attrs={"rows": 5})}


class ApplicationStatusForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [("", "Choose a status")] + [
            (value, label) for value, label in JobApplication.STATUS_CHOICES if value not in {"interview", "withdrawn"}
        ]
        if not self.is_bound and self.instance.status in {"interview", "withdrawn"}:
            self.initial["status"] = ""

    def clean_status(self):
        if self.instance.pk and self.instance.status == "withdrawn":
            raise forms.ValidationError("This application was withdrawn by the candidate and cannot be updated.")
        return self.cleaned_data["status"]

    class Meta:
        model = JobApplication
        fields = ["status"]


class InterviewForm(forms.ModelForm):
    scheduled_start = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    scheduled_end = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    meeting_url = forms.CharField(
        required=False,
        label="Meeting link (Teams, Google Meet, Zoom, etc.)",
    )
    calcom_event_url = forms.CharField(
        required=False,
        label="Optional booking link (Cal.com or other)",
    )

    class Meta:
        model = Interview
        fields = ["scheduled_start", "scheduled_end", "meeting_url", "calcom_event_url", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def _clean_url(self, field_name):
        value = self.cleaned_data.get(field_name, "").strip()
        if not value:
            return ""
        if "://" not in value:
            value = f"https://{value}"
        try:
            URLValidator()(value)
        except ValidationError:
            raise forms.ValidationError("Enter a valid URL, for example https://cal.com/your-link.")
        return value

    def clean_meeting_url(self):
        return self._clean_url("meeting_url")

    def clean_calcom_event_url(self):
        return self._clean_url("calcom_event_url")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("scheduled_start")
        end = cleaned.get("scheduled_end")
        if start and end and end <= start:
            self.add_error("scheduled_end", "End time must be after the start time.")
        return cleaned


class CandidateInterviewForm(forms.ModelForm):
    requested_start = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    requested_end = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    reschedule_reason = forms.CharField(
        required=False,
        label="Reason for rescheduling",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    class Meta:
        model = Interview
        fields = ["requested_start", "requested_end", "reschedule_reason", "candidate_notes"]
        widgets = {
            "candidate_notes": forms.Textarea(attrs={"rows": 5}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("requested_start")
        end = cleaned.get("requested_end")
        if end and not start:
            self.add_error("requested_start", "Choose a start time when specifying an end time.")
        if start and end and end <= start:
            self.add_error("scheduled_end", "End time must be after the start time.")
        return cleaned
