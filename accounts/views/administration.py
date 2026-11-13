"""Staff-only statistics and a dedicated administration sign-in."""

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from applications.models import Interview, JobApplication
from employers.models import Company
from jobs.models import Job
from ..models import Payment, UserProfile
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
    return render(request, 'accounts/administration_dashboard.html', {
        'metrics': metrics, 'statuses': statuses, 'updated_at': now,
        'job_statuses': Job.objects.values('status').annotate(total=Count('pk')).order_by('status'),
        'popular_jobs': popular_jobs,
        'most_popular_job': popular_jobs[0] if popular_jobs and popular_jobs[0].application_total else None,
        'match_statistics': successful_match_statistics(profiles),
        'onboarding_statistics': onboarding_statistics(profiles.only('role', 'profile_data')),
        'staff_accounts': User.objects.filter(is_staff=True, is_active=True).order_by('username'),
        'payment_records': paid_records,
        'payments': paid_records.order_by().values('currency').annotate(total=Sum('amount'), count=Count('pk')).order_by('currency'),
    })


@staff_required
@require_POST
def administration_logout(request):
    logout(request)
    return redirect('administration_login')
