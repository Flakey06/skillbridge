"""Learning pathways and certificate verification submissions."""

from pathlib import Path
import re
from django.contrib import messages
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse
from accounts.notification_helpers import notify
from accounts.decorators import candidate_required
from jobs.models import Job
from matching.services import get_or_update_match, recommend_certifications_for_gap
from ..career_paths import CAREER_PATHS, career_progress
from ..certificate_verification import verify_certificate
from ..models import CandidateMilestone, Certification
from ..services import add_verified_certificate_to_resume
from .common import _current_profile, _selected_career_interests, _career_interest_labels, _context


CERTIFICATE_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}


MAX_CERTIFICATE_FILE_SIZE = 10 * 1024 * 1024


def _certificate_upload_error(uploaded_file):
    """Return a user-facing validation message for certificate evidence."""
    if not uploaded_file:
        return         "Enter your certificate ID before marking this milestone complete."
    extension = Path(uploaded_file.name).suffix.casefold()
    if extension not in CERTIFICATE_FILE_EXTENSIONS:
        return "Certificate evidence must be a PDF, DOC, DOCX, PNG, JPG, or JPEG file."
    if uploaded_file.size > MAX_CERTIFICATE_FILE_SIZE:
        return "Certificate evidence must be 10 MB or smaller."
    return ""


def _certificate_id_error(certificate_id):
    value = (certificate_id or "").strip()
    if len(value) < 6:
        return "Certificate IDs must contain at least 6 characters."
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{4,148}[A-Za-z0-9]", value):
        return "Enter the certificate ID exactly as issued, using only letters, numbers, dots, slashes, underscores, or hyphens."
    return ""


def _catalogue_certification(course, career_key):
    """Represent a curated course as a Certification for milestone tracking."""
    certification, _ = Certification.objects.get_or_create(
        title=course["title"],
        provider=course["provider"],
        defaults={
            "career_area": career_key,
            "skills": ", ".join(course.get("covers", [])),
            "url": course.get("url", ""),
            "is_recognised": True,
        },
    )
    return certification


@candidate_required
def learning(request):
    profile = _current_profile(request)
    data = (profile.profile_data if profile else {}) or {}
    certifications = Certification.objects.filter(is_recognised=True)
    if data.get("career"):
        certifications = certifications.filter(career_area__in=[data["career"], ""])
    milestones = CandidateMilestone.objects.filter(candidate=request.user).select_related("certification")
    interests = _selected_career_interests(data)
    progress = career_progress(request.user, interests)
    requested_direction = request.GET.get("direction", "")
    if requested_direction in interests:
        progress = [goal for goal in progress if goal["key"] == requested_direction]
    course_submissions = {milestone.certification.title: milestone for milestone in milestones}
    completed_courses = {
        milestone.certification.title: milestone
        for milestone in milestones
        if milestone.status == "completed"
    }
    legacy_completed_courses = set(data.get("completed_career_courses", []))
    for goal in progress:
        goal["completed_courses"] = []
        for course in goal["recommendations"]:
            milestone = completed_courses.get(course["title"])
            course["completed"] = bool(milestone or course["title"] in legacy_completed_courses)
            submission = course_submissions.get(course["title"])
            course["certificate_id"] = submission.certificate_id if submission else ""
            course["pending_verification"] = bool(submission and submission.status == "pending_verification")
            course["submission"] = submission
        for milestone in goal["milestones"]:
            for course in milestone["courses"]:
                completed = completed_courses.get(course["title"])
                course["completed"] = bool(completed or course["title"] in legacy_completed_courses)
                submission = course_submissions.get(course["title"])
                course["certificate_id"] = submission.certificate_id if submission else ""
                course["pending_verification"] = bool(submission and submission.status == "pending_verification")
                course["submission"] = submission
        goal["pending_count"] = len({
            course["title"]
            for milestone in goal["milestones"]
            for course in milestone["courses"]
            if course.get("pending_verification")
        })
        visible_titles = {
            course["title"]
            for milestone in goal["milestones"]
            for course in milestone["courses"]
        }
        for completed in milestones:
            certification = completed.certification
            if completed.status != "completed" or certification.title in visible_titles:
                continue
            if certification.career_area not in ("", goal["key"]):
                continue
            goal["completed_courses"].append(
                {
                    "title": certification.title,
                    "provider": certification.provider,
                    "url": certification.url,
                    "certificate_id": completed.certificate_id,
                }
            )
    target_job = None
    match = None
    gap_recommendations = []
    job_id = request.GET.get("job")
    if job_id:
        target_job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)
        if profile and profile.is_pro:
            match = get_or_update_match(request.user, target_job)
            gap_recommendations = recommend_certifications_for_gap(certifications, match.missing_skills)
    if request.method == "POST":
        if request.POST.get("action") == "unsubmit_course":
            milestone = get_object_or_404(
                CandidateMilestone,
                candidate=request.user,
                certification__title=request.POST.get("course_title", ""),
                status="pending_verification",
            )
            if milestone.evidence_file:
                milestone.evidence_file.delete(save=False)
            milestone.delete()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "message": "The verification submission was withdrawn."})
            notify(request.user, "Certificate submission withdrawn", "The verification submission was withdrawn. You can edit and submit it again.", "certificate")
            return redirect(request.get_full_path())

        if request.POST.get("action") == "complete_course":
            ajax_submission = request.headers.get("x-requested-with") == "XMLHttpRequest"

            def submission_error(message):
                if ajax_submission:
                    return JsonResponse({"ok": False, "message": message}, status=400)
                messages.error(request, message)
                return redirect(request.get_full_path())

            career_key = request.POST.get("career_key", "")
            course_title = request.POST.get("course_title", "")
            certificate_id = request.POST.get("certificate_id", "").strip()
            verification_url = request.POST.get("verification_url", "").strip()
            evidence_file = request.FILES.get("evidence_file")
            path = CAREER_PATHS.get(career_key)
            course = next(
                (item for item in (path or {}).get("courses", []) if item["title"] == course_title),
                None,
            )
            upload_error = _certificate_upload_error(evidence_file) if evidence_file else ""
            certificate_id_error = _certificate_id_error(certificate_id)
            if not course:
                return submission_error("That course milestone could not be found. Refresh the page and try again.")
            elif certificate_id_error:
                return submission_error(certificate_id_error)
            else:
                certification = _catalogue_certification(course, career_key)
                result = verify_certificate(certification, verification_url)
                if result.status == "rejected":
                    return submission_error(result.message)
                if result.status != "completed" and not evidence_file:
                    return submission_error("Automatic verification was unavailable. Upload certificate evidence for administrator review.")
                if upload_error:
                    return submission_error(upload_error)
                milestone, _ = CandidateMilestone.objects.get_or_create(
                    candidate=request.user,
                    certification=certification,
                )
                milestone.evidence_file = evidence_file
                milestone.certificate_id = certificate_id
                milestone.verification_url = verification_url
                milestone.verification_method = result.method
                milestone.verification_details = result.message
                milestone.status = result.status
                milestone.verified_at = timezone.now() if result.status == "completed" else None
                milestone.completed_at = milestone.verified_at
                milestone.notes = result.message
                update_fields = ["certificate_id", "verification_url", "verification_method", "verification_details", "verified_at", "status", "completed_at", "notes"]
                if evidence_file:
                    update_fields.append("evidence_file")
                milestone.save(update_fields=update_fields)
                if result.status == "completed":
                    add_verified_certificate_to_resume(request.user, milestone)

                response_message = (
                    f"{course_title} was verified automatically with {certification.provider}."
                    if result.status == "completed"
                    else f"{course_title} was submitted and is pending administrator verification."
                )
                notify(request.user, course_title, response_message, "certificate")
                if ajax_submission:
                    return JsonResponse({
                        "ok": True,
                        "status": result.status,
                        "status_label": milestone.get_status_display(),
                        "message": response_message,
                        "certificate_id": milestone.certificate_id,
                        "course_title": course_title,
                    })
                return redirect(f"{reverse('candidate_learning')}?direction={career_key}#verification-status")

        certification = get_object_or_404(Certification, pk=request.POST.get("certification_id"))
        milestone, _ = CandidateMilestone.objects.get_or_create(candidate=request.user, certification=certification)
        next_status = request.POST.get("status", "in_progress")
        evidence_file = request.FILES.get("evidence_file")
        if next_status == "completed":
            upload_error = _certificate_upload_error(evidence_file or milestone.evidence_file)
            if upload_error:
                messages.error(request, upload_error)
                return redirect(request.get_full_path())
            if evidence_file:
                milestone.evidence_file = evidence_file
            next_status = "pending_verification"
            notify(request.user, "Certificate submitted", "Certificate evidence was submitted for administrator verification.", "certificate")
        milestone.status = next_status
        milestone.completed_at = None
        update_fields = ["status", "completed_at"]
        if evidence_file:
            update_fields.append("evidence_file")
        milestone.save(update_fields=update_fields)
        redirect_url = reverse("candidate_learning")
        if job_id:
            redirect_url = f"{redirect_url}?job={job_id}"
        return redirect(redirect_url)
    return render(
        request,
        "candidates/learning.html",
        _context(
            request,
            profile_data=data,
            certifications=certifications,
            milestones=milestones,
            open_jobs=Job.objects.filter(status="open").select_related("company"),
            target_job=target_job,
            match=match,
            gap_recommendations=gap_recommendations,
            career_progress=progress,
            selected_directions=_career_interest_labels(interests),
        ),
    )


@candidate_required
def verification_status(request):
    """Small polling endpoint used by the learning page after submission."""
    milestones = CandidateMilestone.objects.filter(candidate=request.user).select_related("certification")
    return JsonResponse({
        "certificates": [
            {
                "certification_id": milestone.certification_id,
                "title": milestone.certification.title,
                "status": milestone.status,
                "status_label": milestone.get_status_display(),
                "certificate_id": milestone.certificate_id,
                "details": milestone.verification_details,
            }
            for milestone in milestones
        ]
    })
