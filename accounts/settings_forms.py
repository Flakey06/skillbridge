"""Personal account details, independent of career and company forms."""

from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

from .choices import PHONE_COUNTRY_CODE_CHOICES


class AccountDetailsForm(forms.Form):
    name = forms.CharField(label="Full Name", max_length=150)
    email = forms.EmailField(label="Email Address", max_length=254)
    phone_country_code = forms.ChoiceField(label="Country Code", choices=PHONE_COUNTRY_CODE_CHOICES)
    phone = forms.CharField(
        label="Phone Number", required=False, max_length=30,
        validators=[RegexValidator(r"^[0-9 ()-]+$", "Use digits, spaces, brackets, or hyphens.")],
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel-national"}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if email.casefold() != self.user.email.casefold() and User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email
