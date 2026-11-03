from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ContentItem(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="educational_content",
    )
    class ContentType(models.TextChoices):
        ARTICLE = "article", "Article"
        LESSON = "lesson", "Learning Lesson"
        FAQ = "faq", "Frequently Asked Question"
        RESOURCE = "resource", "Learning Resource"

    class Topic(models.TextChoices):
        PUBERTY = "puberty", "Puberty and Adolescent Development"
        MENSTRUAL_HEALTH = "menstrual_health", "Menstrual Health"
        RELATIONSHIPS = "relationships", "Healthy Relationships and Consent"
        PREGNANCY = "pregnancy_prevention", "Pregnancy Prevention"
        CONTRACEPTION = "contraception", "Contraception"
        REPRODUCTIVE_HEALTH = "reproductive_health", "Sexual and Reproductive Health"
        HEALTH_SERVICES = "health_services", "Accessing Health Services"
        SAFETY = "safety_support", "Safety and Support"
        OTHER = "other", "Other"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        KINYARWANDA = "rw", "Kinyarwanda"

    class Audience(models.TextChoices):
        ADOLESCENTS = "adolescents", "Adolescents and Young People"
        CAREGIVERS = "caregivers", "Parents and Caregivers"
        EDUCATORS = "educators", "Teachers and Educators"
        HEALTH_WORKERS = "health_workers", "Health Workers"
        STAFF = "programme_staff", "Programme Staff"
        GENERAL = "general", "General Audience"

    class ReviewStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "Under Review"
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes Requested"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    content_type = models.CharField(
        max_length=20, choices=ContentType.choices, default=ContentType.ARTICLE
    )
    topic = models.CharField(
        max_length=30, choices=Topic.choices, default=Topic.OTHER
    )
    language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.ENGLISH
    )
    intended_audience = models.CharField(
        max_length=30, choices=Audience.choices, default=Audience.ADOLESCENTS
    )
    summary = models.TextField(blank=True)
    body = models.TextField()

    review_status = models.CharField(
        max_length=25, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT
    )
    is_published = models.BooleanField(default=False)
    is_shared = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Available to other organizations after approval and publication.",
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="content_items_submitted"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="content_items_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_notes = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "title"]
        permissions = [
            ("create_content", "Can create educational content"),
            ("submit_content", "Can submit educational content for review"),
            ("review_content", "Can review educational content"),
            ("publish_content", "Can publish approved educational content"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_published=False) | Q(review_status="approved"),
                name="content_publication_requires_approval",
            )
        ]

    def clean(self):
        super().clean()

        if self.is_shared and (
            not self.is_published
            or self.review_status != self.ReviewStatus.APPROVED
        ):
            raise ValidationError({
                "is_shared": "Only approved and published content can be shared."
            })
        if self.is_published and self.review_status != self.ReviewStatus.APPROVED:
            raise ValidationError(
                {"is_published": "Only approved content can be published."}
            )

    def save(self, *args, **kwargs):
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ContentSource(models.Model):
    content_item = models.ForeignKey(
        ContentItem, on_delete=models.CASCADE, related_name="sources"
    )
    source_organization = models.CharField(max_length=180)
    title = models.CharField(max_length=255)
    url = models.URLField(blank=True)
    last_verified = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_organization", "title"]

    def __str__(self):
        return f"{self.source_organization} — {self.title}"
