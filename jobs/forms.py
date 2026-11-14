from django import forms
from django.utils.html import format_html_join

from candidates.resume_parser import KNOWN_SKILLS

from .models import Job


class FreeChoiceMultipleField(forms.MultipleChoiceField):
    def validate(self, value):
        if self.required and not value:
            raise forms.ValidationError(self.error_messages["required"], code="required")


EVIDENCE_TYPES = ("Projects", "Internship", "Self-proclaimed skills")


class EvidenceRankWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        super().__init__([
            forms.NumberInput(attrs={"min": 1, "max": 3, "step": 1})
            for _ in EVIDENCE_TYPES
        ], attrs)

    def decompress(self, value):
        order = (value or "").split(",")
        return [order.index(item) + 1 if item in order else index + 1
                for index, item in enumerate(EVIDENCE_TYPES)]

    def value_from_datadict(self, data, files, name):
        # CSV imports retain their existing comma-separated order format.
        if not any(f"{name}_{i}" in data for i in range(3)):
            return data.get(name, "")
        return super().value_from_datadict(data, files, name)

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)["widget"]
        return format_html_join("", '<label class="evidence-rank-input">{}<span>{}</span></label>', (
            (widget.render(subwidget["name"], subwidget["value"],
                           subwidget["attrs"], renderer=renderer), label)
            for label, widget, subwidget in zip(EVIDENCE_TYPES, self.widgets, context["subwidgets"])
        ))


class EvidenceRankField(forms.CharField):
    widget = EvidenceRankWidget

    def to_python(self, value):
        if isinstance(value, list):
            if sorted(str(rank) for rank in value) != ["1", "2", "3"]:
                raise forms.ValidationError("Use each rank once: 1, 2 and 3. 1 is most important.")
            return ",".join(item for _, item in sorted(zip(map(int, value), EVIDENCE_TYPES)))
        return super().to_python(value)


class JobForm(forms.ModelForm):
    evidence_types = ("Projects", "Internship", "Self-proclaimed skills")
    skill_catalog = list(dict.fromkeys([
        *KNOWN_SKILLS,
        "FastAPI", "Flask", "Spring Boot", "Node.js", "Vue", "Next.js",
        "REST APIs", "GraphQL", "Machine learning", "Deep learning",
        "Statistics", "Data visualisation", "UI/UX", "User research",
        "Prototyping", "Communication", "Creativity", "Management",
        "Leadership", "Problem solving", "Critical thinking", "Teamwork",
        "Agile", "Scrum", "Product management", "Business analysis",
        "Requirements gathering", "Wireframing", "Usability testing",
        "SEO", "Content writing", "Marketing", "Sales", "Negotiation",
        "Financial analysis", "Risk management", "Accounting", "Research",
    ]))
    skill_choices = [(skill, skill) for skill in skill_catalog]
    required_skill_choices = FreeChoiceMultipleField(
        required=False,
        label="Skills needed",
        choices=skill_choices,
        widget=forms.MultipleHiddenInput(),
    )
    evidence_rank_order = EvidenceRankField(
        required=False,
        label="Rank evidence",
        help_text="Rank each type from 1–3. 1 is most important. Use each rank once.",
    )

    @staticmethod
    def _weight_text(value):
        values = list((value or {}).values())
        maximum = max(values, default=0)
        if maximum > 10:
            return "\n".join(
                f"{label}: {round(float(weight) * 10 / maximum, 1):g}"
                for label, weight in (value or {}).items()
            )
        return "\n".join(f"{label}: {weight:g}" for label, weight in (value or {}).items())

    class Meta:
        model = Job
        fields = [
            "title",
            "role_type",
            "description",
            "industry",
            "location",
            "employment_type",
            "experience_level",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "stipend",
            "required_skills",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "required_skills": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Enter skills separated by commas, for example Python, Django, SQL",
                "autocomplete": "off",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["required_skills"].label = "Skills needed"
        self.fields["required_skills"].help_text = "Enter only the skills required for this job, separated by commas."
        if not self.is_bound and not (self.instance and self.instance.pk):
            self.initial["evidence_rank_order"] = ",".join(self.evidence_types)
        if self.instance and self.instance.pk:
            # Older listings may have preferred skills. Present them in the
            # single skills field so editing does not silently lose them.
            existing = list(dict.fromkeys([
                *self.instance.required_skill_list,
                *self.instance.preferred_skill_list,
            ]))
            field = self.fields["required_skill_choices"]
            known = {value.casefold() for value, _ in field.choices}
            field.choices = [
                *field.choices,
                *((value, value) for value in existing if value.casefold() not in known),
            ]
        if self.instance and self.instance.pk and not self.is_bound:
            existing_order = sorted(
                self.instance.evidence_weights or {},
                key=(self.instance.evidence_weights or {}).get,
                reverse=True,
            )
            self.initial["evidence_rank_order"] = ",".join(existing_order or self.evidence_types)
            self.initial["required_skill_choices"] = existing

    def save(self, commit=True):
        job = super().save(commit=False)
        job.evidence_weights = self.cleaned_data["evidence_weights"]
        job.preferred_skills = ""
        if commit:
            job.save()
            self.save_m2m()
        return job

    def clean(self):
        cleaned = super().clean()
        salary_min = cleaned.get("salary_min")
        salary_max = cleaned.get("salary_max")
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            self.add_error("salary_max", "Maximum salary must be greater than or equal to minimum salary.")
        raw_order = [item.strip() for item in cleaned.get("evidence_rank_order", "").split(",") if item.strip()]
        canonical = {item.casefold(): item for item in self.evidence_types}
        order = []
        for item in raw_order:
            standard = canonical.get(item.casefold())
            if standard and standard not in order:
                order.append(standard)
        order.extend(item for item in self.evidence_types if item not in order)
        rank_values = list(range(len(order), 0, -1))
        total = sum(rank_values)
        cleaned["evidence_weights"] = {
            item: round(value * 100 / total, 4)
            for item, value in zip(order, rank_values)
        }
        canonical = {skill.casefold(): skill for skill in self.skill_catalog}
        for field_name, model_name in (("required_skill_choices", "required_skills"),):
            selected_skills = cleaned.get(field_name) or []
            custom_skills = Job.split_skills(cleaned.get(model_name, ""))
            merged = []
            seen = set()
            for skill in [*selected_skills, *custom_skills]:
                key = skill.casefold()
                standard = canonical.get(key, " ".join(word.capitalize() for word in skill.split()))
                if key not in seen:
                    merged.append(standard)
                    seen.add(key)
            cleaned[model_name] = ", ".join(merged)
        return cleaned


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search jobs")
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any employment type")] + Job.EMPLOYMENT_TYPES,
    )

    required_skills = forms.CharField(
        required=False, label="Required Skills", max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Python, SQL"}),
        help_text="Separate skills with commas. Jobs must require all listed skills.",
    )
    experience_level = forms.ChoiceField(
        required=False, label="Experience Level",
        choices=[("", "Any experience level")] + Job.EXPERIENCE_LEVELS,
    )

    # Upper bounds are exclusive, so adjacent bands have no ambiguous boundary.
    SALARY_RANGES = {
        "under_2000": (None, 2000),
        "2000_3999": (2000, 4000),
        "4000_5999": (4000, 6000),
        "6000_7999": (6000, 8000),
        "8000_plus": (8000, None),
    }
    salary_range = forms.ChoiceField(
        required=False, label="Salary Range (SGD / Month)",
        choices=[
            ("", "Any salary"), ("under_2000", "Under S$2,000"),
            ("2000_3999", "S$2,000–S$3,999"), ("4000_5999", "S$4,000–S$5,999"),
            ("6000_7999", "S$6,000–S$7,999"), ("8000_plus", "S$8,000 and above"),
        ],
    )
