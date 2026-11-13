"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from accounts import views
from accounts.views import administration
from accounts.views import security
from accounts.views.payments import manage_payment_method

urlpatterns = [
    path('administration/', administration.administration_dashboard, name='administration_dashboard'),
    path('administration/certificates/<int:milestone_id>/review/', administration.review_certificate, name='administration_review_certificate'),
    path('administration/users/<int:user_id>/manage/', administration.manage_user, name='administration_manage_user'),
    path('administration/companies/<int:company_id>/review/', administration.review_company, name='administration_review_company'),
    path('administration/jobs/<int:job_id>/review/', administration.review_job, name='administration_review_job'),
    path('administration/reports/<int:report_id>/review/', administration.review_report, name='administration_review_report'),
    path('administration/login/', administration.administration_login, name='administration_login'),
    path('administration/logout/', administration.administration_logout, name='administration_logout'),
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('account/payment-method/', manage_payment_method, name='manage_payment_method'),
    path('account/settings/', security.account_settings, name='account_settings'),
    path('account/security-questions/', security.security_question_settings, name='security_question_settings'),
    path('password-reset/', security.password_reset, name='password_reset'),
    path('password-reset/sent/', security.password_reset_done, name='password_reset_done'),
    path('password-reset/security-questions/', security.security_question_recovery, name='security_question_recovery'),
    path('password-reset/security-questions/hint/', security.security_question_password_hint, name='security_question_password_hint'),
    path('password-reset/<uidb64>/<token>/', security.password_reset_confirm, name='password_reset_confirm'),
    path('password-reset/complete/', security.password_reset_complete, name='password_reset_complete'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('inbox/', views.inbox, name='inbox'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('onboarding/resume/autosave/', views.autosave_resume_draft, name='autosave_resume_draft'),
    path('onboarding/resume/scan/', views.scan_resume_upload, name='scan_resume_upload'),
    path('onboarding/resume/delete/', views.delete_onboarding_resume, name='delete_onboarding_resume'),
    path('plans/', views.plans, name='plans'),
    path('plans/trial/', views.start_pro_trial, name='start_pro_trial'),
    path('plans/checkout/confirm/', views.pro_checkout_confirm, name='pro_checkout_confirm'),
    path('plans/trial/start/', views.start_pro_trial, name='start_pro_trial'),
    path('plans/checkout/', views.start_pro_checkout, name='start_pro_checkout'),
    path('plans/cancel/confirm/', views.cancel_pro_confirm, name='cancel_pro_confirm'),
    path('plans/cancel/', views.cancel_pro, name='cancel_pro'),
    path('plans/success/', views.pro_payment_success, name='pro_payment_success'),
    path('payments/stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('', include('candidates.urls')),
    path('recruiter/', include('employers.urls')),
    path('jobs/', include('jobs.urls')),
    path('resumes/', include('resumes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
