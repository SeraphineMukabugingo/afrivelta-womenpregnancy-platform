import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def make_referral_code():
    return f"AFR-{uuid.uuid4().hex[:12].upper()}"


class ServiceProvider(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="service_providers",
    )
    class Category(models.TextChoices):
        REPRODUCTIVE = "reproductive", "Reproductive Health"
        MATERNAL = "maternal", "Maternal Health"
        MENSTRUAL = "menstrual", "Menstrual Health"
        COUNSELLING = "counselling", "Counselling and Psychosocial Support"
        SAFEGUARDING = "safeguarding", "Protection and Safeguarding"
        GENERAL = "general", "General Healthcare"
        YOUTH = "youth", "Youth Support"
        OTHER = "other", "Other Support Service"

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending Verification"
        VERIFIED = "verified", "Verified"
        NEEDS_REVIEW = "needs_review", "Needs Re-review"
        REJECTED = "rejected", "Not Approved"

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=24, choices=Category.choices)
    description = models.TextField()
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    address = models.CharField(max_length=255)
    district = models.CharField(max_length=100, db_index=True)

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    last_verified = models.DateField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_service_providers",
    )

    is_active = models.BooleanField(default=True)
    is_shared = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Available across organizations after independent verification.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_service_providers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Service provider"
        verbose_name_plural = "Service providers"
        permissions = [
            ("manage_serviceproviders", "Can register and update service providers"),
            ("verify_serviceprovider", "Can independently verify service providers"),
            ("view_verified_provider_directory", "Can access the verified provider directory"),
        ]

    def clean(self):
        if not self.organization_id:
            raise ValidationError({
                "organization": "An owning organization is required."
            })

        if (
            self.is_shared
            and self.verification_status != self.VerificationStatus.VERIFIED
        ):
            raise ValidationError({
                "is_shared": "Only verified providers can be shared."
            })

        if self.verification_status == self.VerificationStatus.VERIFIED:
            if not self.last_verified:
                raise ValidationError(
                    {"last_verified": "A verification date is required."}
                )
            if not self.verified_by_id:
                raise ValidationError(
                    {"verified_by": "A reviewer must verify this provider."}
                )

    def __str__(self):
        return f"{self.name} — {self.get_category_display()}"


class ReferralRecord(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        SHARED = "shared", "Referral Information Shared"
        ACCEPTED = "accepted", "Accepted by Provider"
        CONNECTED = "connected", "Connected with Service"
        COMPLETED = "completed", "Completed"
        FOLLOW_UP = "follow_up", "Follow-up Required"
        CANCELLED = "cancelled", "Cancelled"

    reference_code = models.CharField(
        max_length=20,
        unique=True,
        default=make_referral_code,
        editable=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="referral_records",
    )
    provider = models.ForeignKey(
        ServiceProvider,
        on_delete=models.PROTECT,
        related_name="referrals",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    consent_confirmed = models.BooleanField(default=False)
    referring_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_referral_records",
    )
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_referral_records",
    )
    referral_date = models.DateField(default=timezone.localdate)
    follow_up_due = models.DateField(null=True, blank=True)

    # Do not enter names, contact details, diagnoses, or detailed health records.
    non_identifying_notes = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Referral record"
        verbose_name_plural = "Referral records"
        permissions = [
            ("manage_referrals", "Can manage authorized referral records"),
            ("view_referral_metrics", "Can view aggregate referral metrics"),
        ]

    def clean(self):
        if not self.organization_id:
            raise ValidationError({
                "organization": "An organization is required for every referral."
            })

        if self.provider_id:
            if (
                not self.provider.is_shared
                and self.provider.organization_id != self.organization_id
            ):
                raise ValidationError({
                    "provider": "This provider is not available to this organization."
                })

        if not self.consent_confirmed:
            raise ValidationError(
                {"consent_confirmed": "Confirm appropriate consent before recording this referral."}
            )
        if (
            self.follow_up_due
            and self.referral_date
            and self.follow_up_due < self.referral_date
        ):
            raise ValidationError(
                {"follow_up_due": "Follow-up date cannot precede the referral date."}
            )
        if self.provider_id and (
            not self.provider.is_active
            or self.provider.verification_status
            != ServiceProvider.VerificationStatus.VERIFIED
        ):
            raise ValidationError(
                {"provider": "Only active, verified providers can receive referrals."}
            )

    def __str__(self):
        return f"{self.reference_code} — {self.provider.name}"


class ReferralStatusHistory(models.Model):
    """Audit trail for changes to referral status."""

    referral = models.ForeignKey(
        ReferralRecord,
        on_delete=models.CASCADE,
        related_name="status_history",
    )

    from_status = models.CharField(
        max_length=20,
        choices=ReferralRecord.Status.choices,
        blank=True,
    )

    to_status = models.CharField(
        max_length=20,
        choices=ReferralRecord.Status.choices,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_status_changes",
    )

    changed_at = models.DateTimeField(auto_now_add=True)

    note = models.CharField(
        max_length=300,
        blank=True,
    )

    class Meta:
        ordering = ["changed_at", "pk"]
        verbose_name = "Referral status history"
        verbose_name_plural = "Referral status histories"

    def __str__(self):
        return (
            f"{self.referral.reference_code}: "
            f"{self.from_status or 'Created'} → {self.to_status}"
        )
