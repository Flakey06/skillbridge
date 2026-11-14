from django.urls import path
from . import views

urlpatterns = [
    path("jobs/", views.jobs, name="candidate_jobs"),
    path("saved-jobs/", views.saved_jobs, name="candidate_saved_jobs"),
    path("profile/", views.profile, name="candidate_profile"),
    path("profile/autosave/", views.profile, name="candidate_profile_autosave"),
    path("resume/", views.resume, name="candidate_resume"),
    path("resume/edit/", views.choose_resume_to_edit, name="candidate_resume_select"),
    path("resume/tailor/<slug:interest>/", views.tailor_resume_for_interest, name="tailor_resume_for_interest"),
    path("applications/<int:application_id>/withdraw/", views.withdraw_application, name="candidate_withdraw_application"),
    path("applications/", views.applications, name="candidate_applications"),
    path("calendar/", views.calendar, name="candidate_calendar"),
    path("interviews/<int:interview_id>/", views.interview_room, name="candidate_interview_room"),
    path("learning/", views.learning, name="candidate_learning"),
    path("learning/verification-status/", views.verification_status, name="candidate_verification_status"),
]
