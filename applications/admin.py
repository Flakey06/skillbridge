from django.contrib import admin

from .models import ApplicantEvaluation, ApplicationReviewEvent, CandidateCompanyBlacklist, Interview, JobApplication, SavedJob


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "status", "match_score", "created_at")
    list_filter = ("status",)
    search_fields = ("candidate__username", "job__title", "job__company__name")


@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "created_at")


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("application", "scheduled_start", "created_by")
    list_filter = ("scheduled_start",)


@admin.register(ApplicationReviewEvent)
class ApplicationReviewEventAdmin(admin.ModelAdmin):
    list_display = ("application", "previous_status", "new_status", "reviewer", "created_at")
    list_filter = ("new_status",)


@admin.register(CandidateCompanyBlacklist)
class CandidateCompanyBlacklistAdmin(admin.ModelAdmin):
    list_display = ("candidate", "company", "blocked_by", "created_at")


@admin.register(ApplicantEvaluation)
class ApplicantEvaluationAdmin(admin.ModelAdmin):
    list_display = ("application", "total_score", "recommendation", "reviewed_by", "updated_at")
    list_filter = ("recommendation",)
