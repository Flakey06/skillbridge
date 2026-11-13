from django.urls import path

from . import views

urlpatterns = [
    path("<int:job_id>/report/", views.report_job, name="job_report"),
    path("<int:job_id>/", views.detail, name="job_detail"),
    path("<int:job_id>/save/", views.save_job, name="job_save"),
]
