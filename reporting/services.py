from calendar import monthrange
from datetime import date, datetime

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncMonth, TruncQuarter
from django.utils import timezone

from organizations.access import accessible_organizations
from organizations.models import Organization
from programmes.models import Programme, ProgrammeActivity, ProgrammeMilestone
from content_library.models import ContentItem
from referrals.models import ServiceProvider, ReferralRecord


def reporting_permissions(user):
    """Determine which reporting sections the user may access."""
    if user.is_superuser:
        return {
            "organizations": True,
            "programmes": True,
            "education": True,
            "providers": True,
            "referrals": True,
            "access": True,
        }

    org_admin = (
        user.has_perm("organizations.manage_platform_users")
        or user.has_perm("organizations.manage_organization_members")
    )

    programmes = user.has_perm("programmes.view_programme_analytics")

    education = any(
        user.has_perm(permission)
        for permission in (
            "content_library.create_content",
            "content_library.submit_content",
            "content_library.review_content",
            "content_library.publish_content",
        )
    )

    referrals = (
        user.has_perm("referrals.view_referral_metrics")
        or user.has_perm("referrals.manage_referrals")
    )

    providers = referrals or any(
        user.has_perm(permission)
        for permission in (
            "referrals.manage_serviceproviders",
            "referrals.verify_serviceprovider",
            "referrals.view_verified_provider_directory",
        )
    )

    return {
        "organizations": org_admin,
        "programmes": programmes,
        "education": education,
        "providers": providers,
        "referrals": referrals,
        "access": org_admin or programmes or education or providers or referrals,
    }


def _apply_period(queryset, start_date=None, end_date=None):
    """Filter records by their creation date."""
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)

    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    return queryset


def _status_summary(queryset, field_name, choices):
    """Include all available statuses, even when their count is zero."""
    counts = dict(
        queryset.values(field_name)
        .annotate(total=Count("pk"))
        .values_list(field_name, "total")
    )

    return [
        {
            "value": value,
            "label": label,
            "count": counts.get(value, 0),
        }
        for value, label in choices
    ]


def build_reporting_data(user, start_date=None, end_date=None):
    """Build aggregate metrics within the user's authorized scope."""
    permissions = reporting_permissions(user)

    if not permissions["access"]:
        raise PermissionError("You do not have permission to view reports.")

    if user.is_superuser or permissions["organizations"]:
        organizations = Organization.objects.all()
    else:
        organizations = accessible_organizations(user)

    organization_metrics = None

    if permissions["organizations"]:
        organization_metrics = {
            "total": organizations.count(),
            "active": organizations.filter(
                status=Organization.Status.ACTIVE
            ).count(),
            "pending": organizations.filter(
                status=Organization.Status.PENDING_REVIEW
            ).count(),
            "suspended": organizations.filter(
                status=Organization.Status.SUSPENDED
            ).count(),
            "rejected": organizations.filter(
                status=Organization.Status.REJECTED
            ).count(),
            "statuses": _status_summary(
                organizations, "status", Organization.Status.choices
            ),
        }

    data = {
        "permissions": permissions,
        "organization_metrics": organization_metrics,
        "organization_scope_count": organizations.count(),
        "organization_scope_label": (
            "Platform-wide"
            if user.is_superuser or permissions["organizations"]
            else "Assigned organizations"
        ),
        "organization_scope": list(
            organizations.values(
                "name", "country", "district_or_city"
            ).order_by("name")
        ),
        "programme": None,
        "education": None,
        "providers": None,
        "referrals": None,
        "period_start": start_date,
        "period_end": end_date,
        "generated_at": timezone.localtime(),
    }

    if permissions["programmes"]:
        programmes = Programme.objects.filter(organization__in=organizations)
        programmes = _apply_period(programmes, start_date, end_date)

        activities = ProgrammeActivity.objects.filter(
            programme__organization__in=organizations
        )
        activities = _apply_period(activities, start_date, end_date)

        all_milestones = ProgrammeMilestone.objects.filter(
            programme__organization__in=organizations
        )
        milestones = _apply_period(
            all_milestones, start_date, end_date
        )

        # Use completion_date for completed milestones.
        # For milestones without a completion date, use updated_at.
        evidence_records = all_milestones.filter(
            (
                Q(evidence_summary__gt="")
                & ~Q(evidence_summary__istartswith="Leave blank until")
            )
            |
            (
                Q(evidence_reference__gt="")
                & ~Q(evidence_reference__istartswith="Leave blank until")
            )
        )

        if start_date:
            evidence_records = evidence_records.filter(
                Q(completion_date__gte=start_date)
                | Q(
                    completion_date__isnull=True,
                    updated_at__date__gte=start_date,
                )
            )

        if end_date:
            evidence_records = evidence_records.filter(
                Q(completion_date__lte=end_date)
                | Q(
                    completion_date__isnull=True,
                    updated_at__date__lte=end_date,
                )
            )

        evidence_items = [
            {
                "programme": item.programme.name,
                "title": item.title,
                "status": item.get_status_display(),
                "due_date": item.due_date,
                "completion_date": item.completion_date,
                "evidence_summary": item.evidence_summary,
                "evidence_reference": item.evidence_reference,
            }
            for item in evidence_records.select_related(
                "programme"
            ).order_by("programme__name", "due_date")
        ]

        average_progress = activities.aggregate(
            average=Avg("progress_percent")
        )["average"]

        data["programme"] = {
            "total": programmes.count(),
            "active": programmes.filter(
                status=Programme.Status.ACTIVE
            ).count(),
            "completed": programmes.filter(
                status=Programme.Status.COMPLETED
            ).count(),
            "statuses": _status_summary(
                programmes, "status", Programme.Status.choices
            ),
            "activity_total": activities.count(),
            "activity_completed": activities.filter(
                status=ProgrammeActivity.Status.COMPLETED
            ).count(),
            "activity_average_progress": round(average_progress or 0, 1),
            "activity_statuses": _status_summary(
                activities, "status", ProgrammeActivity.Status.choices
            ),
            "milestone_total": milestones.count(),
            "milestone_achieved": milestones.filter(
                status=ProgrammeMilestone.Status.ACHIEVED
            ).count(),
            "milestone_at_risk": milestones.filter(
                status=ProgrammeMilestone.Status.AT_RISK
            ).count(),
            "milestone_delayed": milestones.filter(
                status=ProgrammeMilestone.Status.DELAYED
            ).count(),
            "milestone_overdue": milestones.filter(
                due_date__lt=timezone.localdate()
            ).exclude(
                status=ProgrammeMilestone.Status.ACHIEVED
            ).count(),
            "milestone_statuses": _status_summary(
                milestones, "status", ProgrammeMilestone.Status.choices
            ),
            "milestone_evidence_count": len(evidence_items),
            "milestone_evidence_items": evidence_items,
        }

    if permissions["education"]:
        # Platform administrators can audit legacy unassigned content.
        # Other users only see content owned by their authorized organizations.
        if user.is_superuser or permissions["organizations"]:
            content = ContentItem.objects.all()
        else:
            content = ContentItem.objects.filter(
                organization__in=organizations
            )

        content = _apply_period(content, start_date, end_date)

        data["education"] = {
            "total": content.count(),
            "unassigned": content.filter(organization__isnull=True).count(),
            "shared": content.filter(is_shared=True).count(),
            "published": content.filter(is_published=True).count(),
            "in_review": content.filter(
                review_status=ContentItem.ReviewStatus.IN_REVIEW
            ).count(),
            "approved": content.filter(
                review_status=ContentItem.ReviewStatus.APPROVED
            ).count(),
            "statuses": _status_summary(
                content, "review_status", ContentItem.ReviewStatus.choices
            ),
        }

    if permissions["providers"]:
        providers = ServiceProvider.objects.filter(
            organization__in=organizations
        )
        providers = _apply_period(providers, start_date, end_date)

        data["providers"] = {
            "total": providers.count(),
            "active": providers.filter(is_active=True).count(),
            "verified": providers.filter(
                verification_status=ServiceProvider.VerificationStatus.VERIFIED
            ).count(),
            "pending": providers.filter(
                verification_status=ServiceProvider.VerificationStatus.PENDING
            ).count(),
            "statuses": _status_summary(
                providers,
                "verification_status",
                ServiceProvider.VerificationStatus.choices,
            ),
            "districts": providers.values("district")
            .annotate(total=Count("pk"))
            .order_by("district"),
        }

    if permissions["referrals"]:
        referrals = ReferralRecord.objects.filter(
            organization__in=organizations
        )
        referrals = _apply_period(referrals, start_date, end_date)

        closed_statuses = [
            ReferralRecord.Status.COMPLETED,
            ReferralRecord.Status.CANCELLED,
        ]

        data["referrals"] = {
            "total": referrals.count(),
            "open": referrals.exclude(status__in=closed_statuses).count(),
            "completed": referrals.filter(
                status=ReferralRecord.Status.COMPLETED
            ).count(),
            "follow_up_overdue": referrals.filter(
                follow_up_due__lt=timezone.localdate()
            ).exclude(status__in=closed_statuses).count(),
            "statuses": _status_summary(
                referrals, "status", ReferralRecord.Status.choices
            ),
        }

    data["trends"] = build_performance_trends(
        user,
        organizations,
        permissions,
        start_date,
        end_date,
    )

    return data


def _month_start(value):
    return date(value.year, value.month, 1)


def _shift_month_start(value, offset):
    index = value.year * 12 + value.month - 1 + offset
    year, month_zero = divmod(index, 12)
    return date(year, month_zero + 1, 1)


def _bucket_start(value, granularity):
    if isinstance(value, datetime):
        value = (
            timezone.localtime(value).date()
            if timezone.is_aware(value)
            else value.date()
        )

    if granularity == "quarter":
        month = ((value.month - 1) // 3) * 3 + 1
        return date(value.year, month, 1)

    return _month_start(value)


def _period_buckets(start_date, end_date, granularity):
    current = _bucket_start(start_date, granularity)
    buckets = []

    while current <= end_date:
        buckets.append(current)

        if granularity == "month":
            current = _shift_month_start(current, 1)
        else:
            current = _shift_month_start(current, 3)

    return buckets


def _event_counts(queryset, event_field, start_date, end_date, granularity):
    """Count records by the date of a specified reporting event."""
    model_field = queryset.model._meta.get_field(event_field)

    queryset = queryset.filter(**{f"{event_field}__isnull": False})

    if model_field.get_internal_type() == "DateTimeField":
        if start_date:
            queryset = queryset.filter(
                **{f"{event_field}__date__gte": start_date}
            )
        if end_date:
            queryset = queryset.filter(
                **{f"{event_field}__date__lte": end_date}
            )
    else:
        if start_date:
            queryset = queryset.filter(
                **{f"{event_field}__gte": start_date}
            )
        if end_date:
            queryset = queryset.filter(
                **{f"{event_field}__lte": end_date}
            )

    truncation = TruncQuarter if granularity == "quarter" else TruncMonth

    results = (
        queryset.annotate(bucket=truncation(event_field))
        .values("bucket")
        .annotate(total=Count("pk"))
    )

    counts = {}

    for item in results:
        if item["bucket"] is not None:
            bucket = _bucket_start(item["bucket"], granularity)
            counts[bucket] = item["total"]

    return counts


def build_performance_trends(
    user,
    organizations,
    permissions,
    start_date=None,
    end_date=None,
):
    """Build monthly and quarterly aggregate event trends."""

    today = timezone.localdate()
    trend_end = end_date or today

    # When the overall report is unrestricted, show the latest
    # twelve calendar months in its trend tables.
    trend_start = start_date or _shift_month_start(
        _month_start(trend_end), -11
    )

    if trend_start > trend_end:
        return {
            "monthly": [],
            "quarterly": [],
            "metrics": [],
            "activity_completion_note": (
                "Activity completion is grouped by last update date."
            ),
        }

    event_specs = {}

    if permissions["programmes"]:
        event_specs["programmes_created"] = (
            Programme.objects.filter(organization__in=organizations),
            "created_at",
            "Programmes created",
        )

        event_specs["activities_completed"] = (
            ProgrammeActivity.objects.filter(
                programme__organization__in=organizations,
                status=ProgrammeActivity.Status.COMPLETED,
            ),
            "updated_at",
            "Completed activities (last updated)",
        )

    if permissions["education"]:
        if user.is_superuser or permissions["organizations"]:
            content = ContentItem.objects.all()
        else:
            content = ContentItem.objects.filter(
                organization__in=organizations
            )

        event_specs["content_created"] = (
            content,
            "created_at",
            "Educational content created",
        )

        event_specs["content_published"] = (
            content.filter(is_published=True),
            "published_at",
            "Educational content published",
        )

    if permissions["providers"]:
        providers = ServiceProvider.objects.filter(
            organization__in=organizations
        )

        event_specs["providers_registered"] = (
            providers,
            "created_at",
            "Providers registered",
        )

        event_specs["providers_verified"] = (
            providers.filter(
                verification_status=ServiceProvider.VerificationStatus.VERIFIED
            ),
            "last_verified",
            "Providers verified",
        )

    if permissions["referrals"]:
        referrals = ReferralRecord.objects.filter(
            organization__in=organizations
        )

        event_specs["referrals_created"] = (
            referrals,
            "created_at",
            "Referrals created",
        )

        event_specs["referrals_completed"] = (
            referrals.filter(status=ReferralRecord.Status.COMPLETED),
            "closed_at",
            "Referrals completed",
        )

    metrics = [
        {"key": key, "label": label}
        for key, (_, _, label) in event_specs.items()
    ]

    def make_rows(granularity):
        buckets = _period_buckets(
            trend_start,
            trend_end,
            granularity,
        )

        counts = {}

        for key, (queryset, event_field, _) in event_specs.items():
            counts[key] = _event_counts(
                queryset,
                event_field,
                trend_start,
                trend_end,
                granularity,
            )

        rows = []

        for bucket in buckets:
            if granularity == "quarter":
                quarter = ((bucket.month - 1) // 3) + 1
                label = f"Q{quarter} {bucket.year}"
            else:
                label = bucket.strftime("%b %Y")

            rows.append({
                "period_label": label,
                "values": [
                    counts[key].get(bucket, 0)
                    for key in event_specs
                ],
            })

        return rows

    return {
        "monthly": make_rows("month"),
        "quarterly": make_rows("quarter"),
        "metrics": metrics,
        "activity_completion_note": (
            "Completed activities are grouped by their last update date "
            "because the activity model does not have a dedicated "
            "completion timestamp."
        ),
        "referral_completion_note": (
            "Completed referrals are grouped by closed_at. Records without "
            "a closure timestamp are not included in this completion trend."
        ),
    }
