"""Company profile editing."""

from django.contrib import messages
from django.shortcuts import redirect, render
from accounts.decorators import recruiter_required
from ..forms import CompanyForm
from .common import _recruiter, _context


@recruiter_required
def company(request):
    recruiter = _recruiter(request)
    company = recruiter.company
    form = CompanyForm(request.POST or None, instance=company)
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
