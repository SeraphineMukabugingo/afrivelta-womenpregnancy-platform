from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Programme(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On Hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="programmes",
    )

    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    objectives = models.TextField()
    target_group = models.CharField(max_length=150)

    country = models.CharField(max_length=100, default="Rwanda")
    district_or_city = models.CharField(max_length=100, blank=True)

    start_date = models.DateField()
    end_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    lead_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_womenpregnancy_programmes",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_womenpregnancy_programmes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("manage_programmes", "Can manage programmes within authorized organizations"),
            ("view_programme_analytics", "Can view programme analytics"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="programme_end_date_on_or_after_start",
            )
        ]

    def __str__(self):
        return f"{self.name} — {self.organization.name}"


class ProgrammeActivity(models.Model):
    class ActivityType(models.TextChoices):
        EDUCATION_SESSION = "education_session", "Education Session"
        COMMUNITY_OUTREACH = "community_outreach", "Community Outreach"
        STAFF_TRAINING = "staff_training", "Staff Training"
        REFERRAL_SUPPORT = "referral_support", "Referral Support"
        MONITORING = "monitoring", "Monitoring and Evaluation"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        ON_HOLD = "on_hold", "On Hold"
        CANCELLED = "cancelled", "Cancelled"

    programme = models.ForeignKey(
        Programme,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    title = models.CharField(max_length=180)
    activity_type = models.CharField(
        max_length=30,
        choices=ActivityType.choices,
        default=ActivityType.EDUCATION_SESSION,
    )
    description = models.TextField(blank=True)

    start_date = models.DateField()
    end_date = models.DateField()

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="womenpregnancy_assigned_activities",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    progress_percent = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="womenpregnancy_created_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_date", "title"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="activity_end_date_on_or_after_start",
            ),
            models.CheckConstraint(
                condition=Q(progress_percent__lte=100),
                name="activity_progress_at_most_100",
            ),
        ]

    def __str__(self):
        return f"{self.title} — {self.programme.name}"


class ProgrammeMilestone(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In Progress"
        ACHIEVED = "achieved", "Achieved"
        AT_RISK = "at_risk", "At Risk"
        DELAYED = "delayed", "Delayed"

    programme = models.ForeignKey(
        Programme,
        on_delete=models.CASCADE,
        related_name="milestones",
    )

    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)

    due_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )

    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="womenpregnancy_responsible_milestones",
    )

    completion_date = models.DateField(
        null=True,
        blank=True,
    )

    evidence_summary = models.TextField(
        blank=True,
        help_text=(
            "Record a concise, non-identifying summary of evidence "
            "supporting milestone progress or completion."
        ),
    )

    evidence_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Optional internal reference to a report or approved "
            "document. Do not include personal health information."
        ),
    )

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="womenpregnancy_created_milestones",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "title"]

    def __str__(self):
        return f"{self.title} — {self.programme.name}"
