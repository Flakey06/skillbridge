"""Server-rendered repeatable profile entries; no browser scripting required."""
import json
from django import forms


class ExperienceEntryForm(forms.Form):
    position = forms.CharField(label="Position / Role", required=False)
    company = forms.CharField(label="Company / Placement", required=False)
    start_date = forms.CharField(label="Start Date", required=False)
    end_date = forms.CharField(label="End Date", required=False)
    current = forms.BooleanField(label="I Currently Work Here", required=False)
    skills = forms.CharField(label="Skills Learned", required=False)
    achievements = forms.CharField(label="Achievements And Responsibilities", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class CertificationEntryForm(forms.Form):
    name = forms.CharField(label="Certificate Name", required=False)
    issuer = forms.CharField(label="Issuer", required=False)
    issue_date = forms.CharField(label="Issue Date", required=False)
    expiry_date = forms.CharField(label="Expiry Date", required=False)
    no_expiry = forms.BooleanField(label="Does Not Expire", required=False)
    credential_id = forms.CharField(label="Certificate ID", required=False)
    skills = forms.CharField(label="Skills Learned", required=False)


ENTRY_TYPES = {"experience": ExperienceEntryForm, "certification": CertificationEntryForm}


def prepare_entries(data):
    """Translate named HTML fields into the existing validated JSON representation."""
    if data is None:
        return None
    result = data.copy()
    for kind, form_type in ENTRY_TYPES.items():
        if f"{kind}_count" not in data:
            continue
        try:
            count = min(50, max(0, int(data.get(f"{kind}_count", 0))))
        except (ValueError, TypeError):
            count = 0
        entries = []
        for index in range(count):
            entry = {name: data.get(f"{kind}-{index}-{name}", "") for name in form_type.base_fields}
            for boolean in ("current", "no_expiry"):
                if boolean in entry:
                    entry[boolean] = bool(entry[boolean])
            entries.append(entry)
        action = data.get("entry_action", "").split(":")
        if action == [kind, "add"] and len(entries) < 50:
            entries.append({})
        elif len(action) == 3 and action[:2] == [kind, "remove"] and action[2].isdigit():
            index = int(action[2])
            if index < len(entries):
                entries.pop(index)
                if not entries:
                    result["experience" if kind == "experience" else "certifications"] = ""
        result[f"{kind}_entries"] = json.dumps(entries)
    return result


def entry_builders(form):
    groups = []
    for kind, form_type in ENTRY_TYPES.items():
        values = form[f"{kind}_entries"].value() or []
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except (TypeError, ValueError):
                values = []
        if not isinstance(values, list):
            values = []
        groups.append({"kind": kind, "title": "Work experience" if kind == "experience" else "Certifications",
                       "rows": [form_type(initial=entry, prefix=f"{kind}-{i}") for i, entry in enumerate(values[:50]) if isinstance(entry, dict)],
                       "field": form[f"{kind}_entries"], "legacy": form["experience" if kind == "experience" else "certifications"]})
    return groups
