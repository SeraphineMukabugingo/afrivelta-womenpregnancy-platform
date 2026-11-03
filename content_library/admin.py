from django.contrib import admin

from .models import ContentItem, ContentSource


class ContentSourceInline(admin.TabularInline):
    model = ContentSource
    extra = 1
    fields = (
        "source_organization",
        "title",
        "url",
        "last_verified",
        "notes",
    )


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "content_type",
        "topic",
        "language",
        "review_status",
        "is_published",
        "updated_at",
    )

    list_filter = (
        "content_type",
        "topic",
        "language",
        "review_status",
        "is_published",
    )

    search_fields = (
        "title",
        "summary",
        "body",
        "reviewer_notes",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "published_at",
    )

    fieldsets = (
        (
            "Educational Content",
            {
                "fields": (
                    "title",
                    "content_type",
                    "topic",
                    "language",
                    "intended_audience",
                    "summary",
                    "body",
                )
            },
        ),
        (
            "Review and Publication",
            {
                "fields": (
                    "review_status",
                    "is_published",
                    "submitted_by",
                    "reviewed_by",
                    "reviewed_at",
                    "reviewer_notes",
                    "published_at",
                )
            },
        ),
        (
            "Recordkeeping",
            {
                "fields": ("created_at", "updated_at")
            },
        ),
    )

    inlines = [ContentSourceInline]
