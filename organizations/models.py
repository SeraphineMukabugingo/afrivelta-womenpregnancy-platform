from django.conf import settings
from django.db import models


class Organization(models.Model):
    class OrganizationType(models.TextChoices):
        NGO = "ngo", "NGO / Civil Society"
        GOVERNMENT = "government", "Government Agency"
        SCHOOL = "school", "School / Education Network"
        HEALTH_PROVIDER = "health_provider", "Health Provider"
        DEVELOPMENT_PARTNER = "development_partner", "Development Partner"
        FOUNDATION = "foundation", "Foundation / Funder"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending Review"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=250, blank=True)
    organization_type = models.CharField(
        max_length=30,
        choices=OrganizationType.choices,
        default=OrganizationType.OTHER,
    )
    country = models.CharField(max_length=100, default="Rwanda")
    district_or_city = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
    )
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_organizations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        ORGANIZATION_ADMIN = "organization_admin", "Organization Admin"
        PROGRAMME_MANAGER = "programme_manager", "Programme Manager"
        MONITORING_EVALUATION = (
            "monitoring_evaluation",
            "Monitoring and Evaluation Officer",
        )
        CONTENT_REVIEWER = "content_reviewer", "Content Reviewer"
        REFERRAL_VERIFIER = "referral_verifier", "Referral Verifier"
        STAFF = "staff", "Staff"

    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.STAFF,
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.INVITED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name", "user__username"]
        permissions = [
            ("manage_platform_users", "Can manage platform user accounts and roles"),
            ("manage_organization_members", "Can manage organization memberships"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_membership",
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.organization} ({self.role})"
