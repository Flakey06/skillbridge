from django import forms

from .choices import INDUSTRY_CHOICES
from .models import Company
from .services import website_logo_url


class CompanyForm(forms.ModelForm):
    name = forms.CharField(label="Name")
    industry = forms.ChoiceField(label="Industry", choices=[("", "Choose an industry")] + INDUSTRY_CHOICES)
    website = forms.CharField(label="Website")
    linkedin_url = forms.CharField(label="LinkedIn URL", required=False)
    linkedin_organization_id = forms.CharField(
        label="LinkedIn Organization ID",
        required=False,
        widget=forms.HiddenInput(),
    )
    logo_url = forms.CharField(label="Logo URL", required=False)
    description = forms.CharField(label="Description", required=False, widget=forms.Textarea(attrs={"rows": 5}))

    class Meta:
        model = Company
        fields = [
            "name",
            "industry",
            "website",
            "linkedin_url",
            "linkedin_organization_id",
            "logo_url",
            "description",
        ]
        widgets = {
            "linkedin_organization_id": forms.HiddenInput(),
        }
        help_texts = {
            "logo_url": "Leave blank to use the company website icon automatically.",
            "linkedin_url": "Optional LinkedIn company page reference.",
        }

    def clean_website(self):
        value = self.cleaned_data.get("website", "").strip()
        if value.startswith("http://"):
            return f"https://{value[7:]}"
        return f"https://{value}" if value and "://" not in value else value

    def clean_linkedin_url(self):
        value = self.cleaned_data.get("linkedin_url", "").strip()
        return f"https://{value}" if value and "://" not in value else value

    def clean_logo_url(self):
        value = self.cleaned_data.get("logo_url", "").strip()
        return f"https://{value}" if value and "://" not in value else value

    def save(self, commit=True):
        company = super().save(commit=False)
        if not company.logo_url:
            company.logo_url = website_logo_url(company.website)
        if commit:
            company.save()
            self.save_m2m()
        return company
