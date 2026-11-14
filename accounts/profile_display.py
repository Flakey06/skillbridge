"""Readable labels for stored profile choices; never alter free-text answers."""
from .choices import (CAREER_CHOICES, SPECIALISATION_CHOICES, EDUCATION_CHOICES,
                      INSTITUTION_CHOICES, VISA_CHOICES, CAREER_STAGE_CHOICES,
                      CAREER_INTEREST_CHOICES)

CHOICE_LABELS = {name: dict(choices) for name, choices in (
    ('career', CAREER_CHOICES), ('specialisation', SPECIALISATION_CHOICES),
    ('education', EDUCATION_CHOICES), ('institution', INSTITUTION_CHOICES),
    ('visa', VISA_CHOICES), ('career_stage', CAREER_STAGE_CHOICES),
    ('career_interests', CAREER_INTEREST_CHOICES),
)}


def profile_label(data, field):
    value = data.get(field, '')
    labels = CHOICE_LABELS.get(field, {})
    if isinstance(value, (list, tuple)):
        return ', '.join(labels.get(item, item) for item in value)
    return labels.get(value, value)


def profile_display_data(data):
    return {**data, **{field: profile_label(data, field) for field in CHOICE_LABELS if field in data}}
