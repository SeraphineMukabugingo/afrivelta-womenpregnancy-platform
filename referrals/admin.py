from django.contrib import admin
from .models import ReferralRecord, ServiceProvider


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "district", "verification_status",
        "last_verified", "is_active",
    )
    list_filter = ("category", "verification_status", "is_active", "district")
    search_fields = ("name", "district", "address")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ReferralRecord)
class ReferralRecordAdmin(admin.ModelAdmin):
    list_display = (
        "reference_code", "provider", "status", "referral_date",
        "follow_up_due", "assigned_staff",
    )
    list_filter = ("status", "referral_date")
    search_fields = ("reference_code", "provider__name")
    readonly_fields = (
        "reference_code", "referring_staff", "created_at",
        "updated_at", "closed_at",
    )
