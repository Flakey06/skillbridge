from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="recruiter_dashboard"),
    path("jobs/", views.listings, name="recruiter_listings"),
    path("jobs/create/", views.create_listing, name="recruiter_create_listing"),
    path("jobs/import/", views.import_listings, name="recruiter_import_listings"),
    path("jobs/template/", views.job_import_template, name="recruiter_job_template"),
    path("jobs/<int:job_id>/", views.job_detail, name="recruiter_job_detail"),
    path("jobs/<int:job_id>/edit/", views.edit_listing, name="recruiter_edit_listing"),
    path("jobs/<int:job_id>/delete/", views.delete_listing, name="recruiter_delete_listing"),
    path("applicants/", views.applicants, name="recruiter_applicants"),
    path("applicants/<int:application_id>/", views.applicant_detail, name="recruiter_applicant_detail"),
    path("calendar/", views.calendar, name="recruiter_calendar"),
    path("company/", views.company, name="recruiter_company"),
    path("company/lookup/", views.company_lookup, name="recruiter_company_lookup"),
]
