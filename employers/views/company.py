"""Company profile editing and lookup."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET
from accounts.decorators import recruiter_required
from ..forms import CompanyForm, CompanyLookupForm
from ..services import lookup_company
from .common import _recruiter, _context


@recruiter_required
def company(request):
    recruiter = _recruiter(request)
    company = recruiter.company
    lookup_form = CompanyLookupForm(request.GET or None)
    lookup_data = None
    lookup_initial = {}
    if request.method == "GET" and lookup_form.is_valid():
        lookup_data = lookup_company(lookup_form.cleaned_data["query"])
        if lookup_data:
            lookup_initial = {key: value for key, value in lookup_data.items() if key in CompanyForm().fields}
        else:
            messages.info(request, "No company record was found. Enter the company details manually.")
    form = CompanyForm(request.POST or None, request.FILES or None, instance=company, initial=lookup_initial)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        profile_photo = form.cleaned_data.get("profile_photo")
        if profile_photo:
            request.user.profile.profile_photo = profile_photo
            request.user.profile.save(update_fields=["profile_photo"])
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
    return render(request, "employers/company.html", _context(request, form=form, company=company, lookup_form=lookup_form, lookup_data=lookup_data))


@recruiter_required
@require_GET
def company_lookup(request):
    query = request.GET.get("q", "")
    result = lookup_company(query)
    return JsonResponse({"query": query, "result": result})
