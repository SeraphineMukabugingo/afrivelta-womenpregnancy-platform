from django.contrib import admin

from .models import (
    Programme,
    ProgrammeActivity,
    ProgrammeMilestone,
)


@admin.register(Programme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "target_group",
        "status",
        "start_date",
        "end_date",
        "lead_user",
    )
    list_filter = ("status", "country", "start_date")
    search_fields = (
        "name",
        "organization__name",
        "target_group",
        "district_or_city",
    )
    date_hierarchy = "start_date"
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProgrammeActivity)
class ProgrammeActivityAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "programme",
        "activity_type",
        "status",
        "progress_percent",
        "start_date",
        "end_date",
        "assigned_to",
    )
    list_filter = ("activity_type", "status", "start_date")
    search_fields = (
        "title",
        "programme__name",
        "programme__organization__name",
    )
    date_hierarchy = "start_date"
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProgrammeMilestone)
class ProgrammeMilestoneAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "programme",
        "due_date",
        "status",
        "responsible_user",
        "completion_date",
    )
    list_filter = ("status", "due_date")
    search_fields = (
        "title",
        "programme__name",
        "programme__organization__name",
        "evidence_reference",
    )
    date_hierarchy = "due_date"
    readonly_fields = ("created_at", "updated_at")
