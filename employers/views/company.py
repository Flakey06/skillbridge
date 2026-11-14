"""Company profile editing."""

from django.contrib import messages
from django.shortcuts import redirect, render
from accounts.decorators import recruiter_required
from ..forms import CompanyForm
from ..services import company_matches
from .common import _recruiter, _context


@recruiter_required
def company(request):
    recruiter = _recruiter(request)
    company = recruiter.company
    form_data = request.POST.copy() if request.method == "POST" else None
    lookup_match = None
    if form_data is not None and request.POST.get("action") == "find_company":
        matches = company_matches(form_data.get("name"))
        lookup_match = matches[0] if matches else None
        if lookup_match:
            form_data["name"] = lookup_match["name"]
            form_data["website"] = lookup_match["website"]
            form_data["logo_url"] = lookup_match["logo_url"]
        form = CompanyForm(form_data, instance=company)
        return render(request, "employers/company.html", _context(
            request, form=form, company=company, lookup_match=lookup_match,
            lookup_attempted=True,
        ))
    form = CompanyForm(form_data, instance=company)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        recruiter.company = company
        recruiter.save(update_fields=["company"])
        profile = request.user.profile
        profile_data = dict(profile.profile_data or {})
        profile_data.update({
            "company": company.name,
            "website": company.website,
            "industry": company.industry,
        })
        profile.profile_data = profile_data
        profile.save(update_fields=["profile_data"])
        messages.success(request, "Company profile saved.")
        return redirect("recruiter_company")
    return render(request, "employers/company.html", _context(request, form=form, company=company))
