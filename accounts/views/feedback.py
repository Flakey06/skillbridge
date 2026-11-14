from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.db.models import Q

from jobs.models import Job
from ..models import SiteFeedback


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = SiteFeedback
        fields = ["category", "job", "rating", "message"]
        labels = {
            "job": "Related job (optional)",
            "rating": "Overall rating (optional)",
            "message": "Your comments",
        }
        widgets = {
            "rating": forms.Select(choices=[("", "No rating")] + [(number, f"{number} of 5") for number in range(1, 6)]),
            "message": forms.Textarea(attrs={"rows": 7, "placeholder": "Tell us what worked, what was confusing, or what we should improve."}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        jobs = Job.objects.select_related("company").order_by("-created_at")
        role = getattr(getattr(user, "profile", None), "role", "")
        if role == "recruiter":
            jobs = jobs.filter(created_by=user)
        else:
            jobs = jobs.filter(Q(status="open") | Q(applications__candidate=user)).distinct()
        self.fields["job"].queryset = jobs
        self.fields["job"].empty_label = "Not about a specific job"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("category") == "job" and not cleaned.get("job"):
            self.add_error("job", "Choose the job this feedback is about.")
        return cleaned


@login_required
def feedback(request):
    profile = getattr(request.user, "profile", None)
    role = profile.role if profile and profile.role in {"candidate", "recruiter"} else "candidate"
    form = FeedbackForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.user = request.user
        entry.save()
        messages.success(request, "Thank you. Your feedback was sent to the SkillBridge team.")
        return redirect("feedback")
    return render(request, "accounts/feedback.html", {
        "form": form, "role": role,
        "feedback_history": SiteFeedback.objects.filter(user=request.user)[:10],
    })
