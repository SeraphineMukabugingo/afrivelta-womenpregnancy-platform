from django.contrib import admin
from .models import Organization, OrganizationMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization_type",
        "country",
        "district_or_city",
        "status",
        "created_at",
    )
    list_filter = ("organization_type", "country", "status")
    search_fields = ("name", "legal_name", "contact_email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "user",
        "role",
        "status",
        "created_at",
    )
    list_filter = ("role", "status", "organization")
    search_fields = (
        "organization__name",
        "user__username",
        "user__email",
    )
    readonly_fields = ("created_at",)
