from django.contrib import admin, messages

from .models import Payment, Referral, SecurityQuestionAnswer, UserProfile
from .referral_services import award_referral
from .payment_services import set_stripe_entitlement


class StripePaymentStateFilter(admin.SimpleListFilter):
    title = "Stripe payment state"
    parameter_name = "stripe_state"

    def lookups(self, request, model_admin):
        return (
            ("never_paid", "Never paid"),
            ("attention", "Needs attention"),
            ("paid", "Paid"),
        )

    def queryset(self, request, queryset):
        if self.value() == "never_paid":
            return queryset.exclude(user__payments__provider="stripe", user__payments__paid_at__isnull=False).distinct()
        if self.value() == "attention":
            return queryset.filter(
                user__payments__provider="stripe",
                user__payments__status__in=("pending", "past_due", "expired", "failed", "cancelled"),
            ).distinct()
        if self.value() == "paid":
            return queryset.filter(user__payments__provider="stripe", user__payments__status="paid").distinct()
        return queryset


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "plan", "pro_access", "stripe_payment_state", "plan_expires_at")
    list_filter = ("role", "plan", StripePaymentStateFilter)
    search_fields = ("user__username", "user__email")
    actions = ("revoke_pro_access",)

    @admin.display(boolean=True, description="Pro active")
    def pro_access(self, profile):
        return profile.is_pro

    @admin.display(description="Latest Stripe status")
    def stripe_payment_state(self, profile):
        payments = profile.user.payments.filter(provider="stripe").order_by("-created_at")
        latest = payments.first()
        if latest is None:
            return "Never attempted"
        if not payments.filter(paid_at__isnull=False).exists():
            return f"Never paid ({latest.get_status_display()})"
        return latest.get_status_display()

    @admin.action(description="Revoke Pro access for selected users")
    def revoke_pro_access(self, request, queryset):
        updated = queryset.update(plan="free", plan_expires_at=None)
        self.message_user(request, f"Revoked Pro access for {updated} user(s).", messages.SUCCESS)


@admin.register(SecurityQuestionAnswer)
class SecurityQuestionAnswerAdmin(admin.ModelAdmin):
    list_display = ("user", "position", "question")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("answer_hash",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "provider",
        "amount",
        "currency",
        "status",
        "user_plan",
        "subscription_id",
        "created_at",
        "paid_at",
    )
    list_filter = ("provider", "status", "created_at", "paid_at")
    search_fields = ("user__username", "user__email", "external_id")
    readonly_fields = ("created_at", "paid_at", "metadata")
    actions = ("revoke_pro_for_payments",)
    date_hierarchy = "created_at"

    @admin.display(description="Current plan")
    def user_plan(self, payment):
        profile = getattr(payment.user, "profile", None)
        return profile.get_plan_display() if profile else "No profile"

    @admin.display(description="Stripe subscription")
    def subscription_id(self, payment):
        return (payment.metadata or {}).get("subscription", "—")

    @admin.action(description="Mark selected payments failed and revoke Pro")
    def revoke_pro_for_payments(self, request, queryset):
        updated = 0
        for payment in queryset.filter(provider="stripe").select_related("user"):
            set_stripe_entitlement(
                payment,
                active=False,
                status="failed",
                stripe_status="admin_revoked",
            )
            updated += 1
        self.message_user(request, f"Revoked Pro access for {updated} Stripe payment(s).", messages.SUCCESS)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("referrer", "referred_user", "status", "reward_days", "created_at", "rewarded_at")
    list_filter = ("status", "created_at")
    search_fields = ("referrer__username", "referrer__email", "referred_user__username", "referred_user__email", "referral_code")
    readonly_fields = ("created_at", "rewarded_at", "metadata")
    actions = ("retry_rewards",)

    @admin.action(description="Retry selected referral rewards")
    def retry_rewards(self, request, queryset):
        rewarded = 0
        for referral in queryset.select_related("referrer__profile", "referred_user__profile"):
            award_referral(referral)
            rewarded += referral.status == "rewarded"
        self.message_user(request, f"{rewarded} referral reward(s) are fully applied.", messages.SUCCESS)
