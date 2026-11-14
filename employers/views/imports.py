"""CSV and Excel listing templates and bulk imports."""

from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.http import require_http_methods
import csv
import io
import secrets
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET
from accounts.decorators import recruiter_required
from jobs.imports import (
    IMPORT_FIELDS,
    REQUIRED_FIELDS,
    import_instructions,
    read_import,
    template_example,
    template_headers,
    validate_import,
)
from .common import _recruiter, _context


@recruiter_required
@require_GET
def job_import_template(request):
    example = template_example()
    if request.GET.get("format") == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Jobs"
        sheet.append(template_headers())
        sheet.append([example[field] for field in IMPORT_FIELDS])
        sheet.freeze_panes = "A2"
        for index, field in enumerate(IMPORT_FIELDS, start=1):
            cell = sheet.cell(1, index)
            cell.font = Font(bold=True, color="C62828" if field in REQUIRED_FIELDS else "172447")
            sheet.column_dimensions[cell.column_letter].width = 28
        instructions = workbook.create_sheet("Instructions")
        for row in import_instructions():
            instructions.append(row)
        instructions.column_dimensions["A"].width = 24
        instructions.column_dimensions["B"].width = 110
        output = io.BytesIO()
        workbook.save(output)
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="skillbridge-job-template.xlsx"'
    else:
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="skillbridge-job-template.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(template_headers())
        writer.writerow([example[field] for field in IMPORT_FIELDS])
    return response


@recruiter_required
@require_http_methods(["GET", "POST"])
def import_listings(request):
    recruiter = _recruiter(request)
    errors = []
    preview = []
    token = ""
    if request.method == "GET":
        request.session.pop("job_import_preview", None)
    if request.method == "POST" and recruiter.company_id:
        if request.POST.get("action") == "confirm":
            pending = request.session.get("job_import_preview") or {}
            if (not pending or pending.get("company_id") != recruiter.company_id
                    or not secrets.compare_digest(str(pending.get("token", "")), request.POST.get("token", ""))
                    or timezone.now().timestamp() - pending.get("created_at", 0) > 1800):
                messages.error(request, "This preview has expired or changed. Upload the file again.")
            else:
                forms, errors = validate_import(pending["rows"])
                if not errors:
                    with transaction.atomic():
                        for form in forms:
                            job = form.save(commit=False)
                            job.company = recruiter.company
                            job.created_by = request.user
                            job.save()
                    request.session.pop("job_import_preview", None)
                    messages.success(request, f"Created {len(forms)} job listing(s).")
                    return redirect("recruiter_listings")
        else:
            request.session.pop("job_import_preview", None)
            upload = request.FILES.get("file")
            if not upload:
                messages.error(request, "Choose a CSV or Excel .xlsx file.")
            else:
                try:
                    rows = read_import(upload)
                    forms, errors = validate_import(rows)
                    if not errors:
                        token = secrets.token_hex(24)
                        request.session["job_import_preview"] = {
                            "rows": rows, "company_id": recruiter.company_id,
                            "token": token, "created_at": timezone.now().timestamp(),
                        }
                        preview = [form.save(commit=False) for form in forms]
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
    elif request.method == "POST":
        messages.error(request, "Complete your company profile before importing listings.")
    return render(request, "employers/import_listings.html", _context(
        request, company=recruiter.company, errors=errors, preview=preview,
        token=token, instructions=import_instructions(),
    ))
