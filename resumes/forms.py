from django import forms

from .models import TailoredResume


class TailoredResumeForm(forms.ModelForm):
    class Meta:
        model = TailoredResume
        fields = ["title", "content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 28}),
        }
