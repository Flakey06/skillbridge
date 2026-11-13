"""Read job spreadsheets without publishing until the recruiter confirms."""

import csv
import io
from pathlib import Path
import zipfile

from django.core.exceptions import ValidationError

from .forms import JobForm
from .models import Job


MAX_IMPORT_ROWS = 100
MAX_IMPORT_BYTES = 2 * 1024 * 1024
# Keep bulk imports simple: spreadsheet skills are treated as required skills.
# Recruiters can still add preferred skills later from the normal edit form.
IMPORT_FIELDS = tuple(
    field for field in JobForm.Meta.fields if field != "preferred_skills"
) + ("evidence_rank_order",)
REQUIRED_FIELDS = ("title", "description", "employment_type")
DEFAULTS = {
    "role_type": "other", "experience_level": "entry", "status": "open",
    "salary_currency": "SGD", "salary_period": "month",
}


def template_headers():
    return [field + (" *" if field in REQUIRED_FIELDS else "") for field in IMPORT_FIELDS]


def template_example():
    return {
        **dict.fromkeys(IMPORT_FIELDS, ""), **DEFAULTS,
        "title": "Backend developer", "description": "Build and maintain Python web services.",
        "employment_type": "full_time", "required_skills": "Python, Django, SQL",
        "location": "Singapore", "salary_min": "4000", "salary_max": "6000",
        "evidence_rank_order": "Internship,Projects,Self-proclaimed skills",
    }


def import_instructions():
    instructions = [
        ("Required columns", "title, description, employment_type. Required headers have a red asterisk in Excel and * in CSV."),
        ("Rows", "One listing per row; maximum 100 listings and 2 MB. Replace or delete the example row before uploading."),
        ("Company", "All rows belong to your current company and recruiter account. Do not add company or recruiter columns."),
        ("Optional defaults", ", ".join(f"{key}={value}" for key, value in DEFAULTS.items())),
        ("Required skills", "Use the required_skills column and separate skills with commas. To keep bulk imports simple, preferred skills are not included; add them later when editing a listing if needed."),
        ("Evidence order", "List Projects, Internship, Self-proclaimed skills in most-to-least important order, separated by commas."),
        ("Salary", "Optional nonnegative whole numbers; maximum must be at least minimum."),
        ("Confirmation", "Upload validates every row. No listings are saved until you confirm the preview."),
        ("Excel format", "Use .xlsx, with listings on the first sheet. Legacy .xls and formulas are not supported."),
    ]
    for field in ("role_type", "industry", "employment_type", "experience_level", "salary_currency", "salary_period", "status"):
        instructions.append((field, "; ".join(f"{value} ({label})" for value, label in Job._meta.get_field(field).choices)))
    return instructions


def read_import(upload):
    if upload.size > MAX_IMPORT_BYTES:
        raise ValidationError("Upload a file of 2 MB or smaller.")
    extension = Path(upload.name).suffix.casefold()
    if extension not in {".csv", ".xlsx"}:
        raise ValidationError("Upload a CSV or Excel .xlsx file.")
    try:
        if extension == ".csv":
            rows = csv.reader(io.StringIO(upload.read().decode("utf-8-sig")), strict=True)
            return _read_rows(rows)
        from openpyxl import load_workbook

        # Bound the expanded archive before parsing a compressed workbook.
        with zipfile.ZipFile(upload) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20 * 1024 * 1024:
                raise ValidationError("This workbook is too large when expanded. Export a smaller CSV instead.")
        upload.seek(0)
        workbook = load_workbook(upload, read_only=True, data_only=False)
        try:
            def cells():
                for row in workbook.worksheets[0].iter_rows():
                    if any(cell.data_type == "f" for cell in row):
                        raise ValidationError("Formulas are not supported. Replace formulas with their values before uploading.")
                    yield [cell.value for cell in row]
            return _read_rows(cells())
        finally:
            workbook.close()
    except ValidationError:
        raise
    except ImportError:
        raise ValidationError("Excel support is unavailable. Use the CSV template or install the project requirements.")
    except Exception:
        raise ValidationError("The file could not be read. Use a UTF-8 CSV or a valid .xlsx workbook.")


def _read_rows(rows):
    iterator = iter(rows)
    header = next(iterator, None)
    if not header:
        raise ValidationError("The file is empty. Start with a job template.")
    headers = [str(value or "").strip().rstrip("*").strip().casefold() for value in header]
    # Excel may include trailing formatted but unused columns.
    while headers and not headers[-1]:
        headers.pop()
    if len(headers) != len(set(headers)) or any(not field for field in headers):
        raise ValidationError("Column names must be nonblank and unique.")
    unknown = set(headers) - set(IMPORT_FIELDS)
    missing = set(REQUIRED_FIELDS) - set(headers)
    if unknown or missing:
        raise ValidationError("Check the template columns. " +
                              (f"Unknown: {', '.join(sorted(unknown))}. " if unknown else "") +
                              (f"Required: {', '.join(sorted(missing))}." if missing else ""))
    result = []
    for number, values in enumerate(iterator, start=2):
        if number > MAX_IMPORT_ROWS + 1:
            raise ValidationError("Use at most 100 data rows per file, without extra blank rows.")
        values = ["" if value is None else str(value).strip() for value in values]
        if not any(values):
            continue
        if any(values[len(headers):]):
            raise ValidationError(f"Row {number} has values beyond the template columns.")
        data = dict(zip(headers, values))
        for field, default in DEFAULTS.items():
            data[field] = data.get(field) or default
        result.append({"row": number, "data": data})
    if not result:
        raise ValidationError("Add at least one listing below the header row.")
    return result


def validate_import(rows):
    forms = []
    errors = []
    for row in rows:
        data = dict(row["data"])
        # Accept either documented database values or their display labels.
        for field in ("role_type", "industry", "employment_type", "experience_level", "salary_currency", "salary_period", "status"):
            value = str(data.get(field, ""))
            choices = {str(key).casefold(): key for key, _ in Job._meta.get_field(field).choices}
            choices.update({str(label).casefold(): key for key, label in Job._meta.get_field(field).choices})
            data[field] = choices.get(value.casefold(), value)
        form = JobForm(data=data)
        valid = form.is_valid()
        order = [item.strip().casefold() for item in data.get("evidence_rank_order", "").split(",") if item.strip()]
        if order and (len(order) != 3 or set(order) != {item.casefold() for item in JobForm.evidence_types}):
            form.add_error("evidence_rank_order", "List all three evidence types once, in most-to-least important order.")
            valid = False
        if valid:
            forms.append(form)
        else:
            errors.append({"row": row["row"], "fields": form.errors})
    return forms, errors
