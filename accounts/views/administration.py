"""Staff-only statistics and a dedicated administration sign-in."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from applications.models import Interview, JobApplication
from candidates.models import CandidateMilestone
from candidates.services import add_verified_certificate_to_resume
from employers.models import Company
from jobs.models import Job
from accounts.notification_helpers import notify
from ..models import AdminAuditLog, ModerationReport, Payment, UserProfile
from ..administration_stats import onboarding_statistics, successful_match_statistics


class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise self.get_invalid_login_error()


staff_required = user_passes_test(
    lambda user: user.is_authenticated and user.is_active and user.is_staff,
    login_url=reverse_lazy('administration_login'),
)


def _audit(request, action, target, details=''):
    AdminAuditLog.objects.create(
        actor=request.user, action=action, target_type=target._meta.verbose_name,
        target_id=str(target.pk), target_label=str(target), details=details,
    )


def _dashboard_section(name, query=''):
    return redirect(f"{reverse_lazy('administration_dashboard')}{query}#{name}")


@never_cache
def administration_login(request):
    if request.user.is_authenticated and request.user.is_active and request.user.is_staff:
        return redirect('administration_dashboard')
    form = StaffAuthenticationForm(request, data=request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect('administration_dashboard')
    return render(request, 'accounts/administration_login.html', {'form': form})


@staff_required
@never_cache
def administration_dashboard(request):
    now = timezone.now()
    profiles = UserProfile.objects.filter(user__is_staff=False)
    applications = JobApplication.objects.all()
    application_count = applications.count()
    counts = dict(applications.values('status').annotate(total=Count('pk')).values_list('status', 'total'))
    statuses = [
        {'label': label, 'count': counts.get(value, 0),
         'percentage': round(counts.get(value, 0) / application_count * 100) if application_count else 0}
        for value, label in JobApplication.STATUS_CHOICES
    ]
    metrics = [
        ('Candidates', profiles.filter(role='candidate').count()),
        ('Recruiters', profiles.filter(role='recruiter').count()),
        ('Companies', Company.objects.count()),
        ('Open Jobs', Job.objects.filter(status='open').count()),
        ('Total Applications', application_count),
        ('Upcoming Interviews', Interview.objects.filter(scheduled_start__gte=now).exclude(application__status='withdrawn').count()),
        ('Active Pro Accounts', profiles.filter(plan='pro').filter(Q(plan_expires_at__isnull=True) | Q(plan_expires_at__gt=now)).count()),
        ('Staff Accounts', User.objects.filter(is_staff=True, is_active=True).count()),
    ]
    popular_jobs = list(Job.objects.select_related('company').annotate(application_total=Count('applications')).order_by('-application_total', '-created_at', '-pk')[:5])
    paid_records = Payment.objects.filter(Q(status='paid') | Q(paid_at__isnull=False)).select_related('user', 'user__profile').order_by('-paid_at', '-created_at')
    certificate_submissions = CandidateMilestone.objects.filter(status='pending_verification').select_related('candidate', 'certification').order_by('created_at')
    certificate_history = CandidateMilestone.objects.exclude(reviewed_at=None).select_related('candidate', 'certification', 'reviewed_by').order_by('-reviewed_at')[:50]
    user_query = request.GET.get('user_q', '').strip()
    managed_users = User.objects.filter(is_staff=False).select_related('profile')
    if user_query:
        managed_users = managed_users.filter(Q(username__icontains=user_query) | Q(email__icontains=user_query) | Q(first_name__icontains=user_query) | Q(last_name__icontains=user_query))
    member_statistics = []
    for profile in profiles.select_related('user', 'user__recruiter_profile__company'):
        profile_data = profile.profile_data or {}
        if profile.role == 'recruiter':
            recruiter_profile = getattr(profile.user, 'recruiter_profile', None)
            company = getattr(recruiter_profile, 'company', None)
            category = company.get_industry_display() if company and company.industry else 'Recruiter · No industry'
        else:
            category = str(
                profile_data.get('career')
                or profile_data.get('career_area')
                or profile_data.get('specialisation')
                or 'Candidate · Career not set'
            ).strip()
        member_statistics.append({
            'joined': profile.user.date_joined.date().isoformat(),
            'role': profile.role,
            'category': category,
        })
    return render(request, 'accounts/administration_dashboard.html', {
        'metrics': metrics, 'statuses': statuses, 'updated_at': now,
        'job_statuses': Job.objects.values('status').annotate(total=Count('pk')).order_by('status'),
        'popular_jobs': popular_jobs,
        'most_popular_job': popular_jobs[0] if popular_jobs and popular_jobs[0].application_total else None,
        'match_statistics': successful_match_statistics(profiles),
        'onboarding_statistics': onboarding_statistics(profiles.only('role', 'profile_data')),
        'staff_accounts': User.objects.filter(is_staff=True, is_active=True).order_by('username'),
        'payment_records': paid_records,
        'certificate_submissions': certificate_submissions,
        'certificate_history': certificate_history,
        'managed_users': managed_users.order_by('username')[:50],
        'user_query': user_query,
        'companies_for_review': Company.objects.filter(verification_status='pending').order_by('name'),
        'company_history': Company.objects.exclude(reviewed_at=None).select_related('reviewed_by').order_by('-reviewed_at')[:30],
        'moderation_reports': ModerationReport.objects.select_related('reporter', 'moderator').order_by('status', '-created_at')[:50],
        'audit_logs': AdminAuditLog.objects.select_related('actor')[:100],
        'member_statistics': member_statistics,
        'payments': paid_records.order_by().values('currency').annotate(total=Sum('amount'), count=Count('pk')).order_by('currency'),
    })


@staff_required
@require_POST
def review_certificate(request, milestone_id):
    milestone = CandidateMilestone.objects.select_related('candidate', 'certification').filter(
        pk=milestone_id, status='pending_verification',
    ).first()
    if milestone is None:
        return _dashboard_section('certifications')

    decision = request.POST.get('decision')
    comment = request.POST.get('comment', '').strip()
    if decision == 'reject' and not comment:
        messages.error(request, 'A rejection reason is required so the candidate can correct the submission.')
        return _dashboard_section('certifications')
    milestone.verification_method = 'admin_review'
    if decision == 'approve':
        reviewed_at = timezone.now()
        milestone.status = 'completed'
        milestone.completed_at = reviewed_at
        milestone.verified_at = reviewed_at
        milestone.verification_details = comment or f'Approved by administrator {request.user.get_username()}.'
    elif decision == 'reject':
        milestone.status = 'rejected'
        milestone.completed_at = None
        milestone.verified_at = None
        milestone.verification_details = comment
    else:
        return _dashboard_section('certifications')
    milestone.notes = milestone.verification_details
    milestone.reviewed_by = request.user
    milestone.review_comment = comment
    milestone.reviewed_at = timezone.now()
    milestone.save(update_fields=[
        'status', 'completed_at', 'verified_at', 'verification_method',
        'verification_details', 'notes', 'reviewed_by', 'review_comment', 'reviewed_at',
    ])
    if decision == 'approve':
        add_verified_certificate_to_resume(milestone.candidate, milestone)
        notify(milestone.candidate, 'Certification approved', f'{milestone.certification.title} has been verified.', 'certificate')
    else:
        notify(milestone.candidate, 'Certification needs changes', f'{milestone.certification.title}: {comment}', 'certificate')
    _audit(request, f'certificate_{decision}', milestone, comment)
    return _dashboard_section('certifications')


@staff_required
@require_POST
def manage_user(request, user_id):
    user = get_object_or_404(User, pk=user_id, is_staff=False)
    action = request.POST.get('action')
    if action not in {'suspend', 'restore'}:
        return _dashboard_section('users')
    user.is_active = action == 'restore'
    user.save(update_fields=['is_active'])
    _audit(request, f'user_{action}', user, request.POST.get('comment', '').strip())
    messages.success(request, f'{user.username} was {"restored" if user.is_active else "suspended"}.')
    return _dashboard_section('users', f'?user_q={user.username}')


@staff_required
@require_POST
def review_company(request, company_id):
    company = get_object_or_404(Company, pk=company_id)
    decision = request.POST.get('decision')
    comment = request.POST.get('comment', '').strip()
    if decision not in {'approve', 'reject'} or (decision == 'reject' and not comment):
        messages.error(request, 'A rejection reason is required.')
        return _dashboard_section('employers')
    company.verification_status = 'verified' if decision == 'approve' else 'rejected'
    company.verification_comment = comment
    company.reviewed_by = request.user
    company.reviewed_at = timezone.now()
    company.save(update_fields=['verification_status', 'verification_comment', 'reviewed_by', 'reviewed_at'])
    for recruiter in company.recruiters.select_related('user'):
        notify(recruiter.user, f'Company {company.verification_status}', comment or f'{company.name} was approved.', 'moderation')
    _audit(request, f'company_{decision}', company, comment)
    return _dashboard_section('employers')


@staff_required
@require_POST
def review_report(request, report_id):
    report = get_object_or_404(ModerationReport, pk=report_id)
    decision = request.POST.get('decision')
    if decision not in {'resolve', 'dismiss'}:
        return _dashboard_section('reports')
    report.status = 'resolved' if decision == 'resolve' else 'dismissed'
    report.moderator = request.user
    report.resolution_note = request.POST.get('comment', '').strip()
    report.resolved_at = timezone.now()
    report.save(update_fields=['status', 'moderator', 'resolution_note', 'resolved_at'])
    if report.reporter:
        notify(report.reporter, 'Report reviewed', f'Your report about {report.subject_label} was {report.status}.', 'moderation')
    _audit(request, f'report_{decision}', report, report.resolution_note)
    return _dashboard_section('reports')


@staff_required
@require_POST
def administration_logout(request):
    logout(request)
    return redirect('administration_login')
