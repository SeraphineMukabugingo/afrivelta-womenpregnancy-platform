from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from organizations.access import accessible_organizations
from django.views.decorators.http import require_POST

from .forms import ReferralRecordForm, ServiceProviderForm
from .models import ReferralRecord, ReferralStatusHistory, ServiceProvider


# Only these referral status transitions are permitted.
REFERRAL_STATUS_TRANSITIONS = {
    ReferralRecord.Status.NEW: {
        ReferralRecord.Status.SHARED,
        ReferralRecord.Status.FOLLOW_UP,
        ReferralRecord.Status.CANCELLED,
    },
    ReferralRecord.Status.SHARED: {
        ReferralRecord.Status.ACCEPTED,
        ReferralRecord.Status.FOLLOW_UP,
        ReferralRecord.Status.CANCELLED,
    },
    ReferralRecord.Status.ACCEPTED: {
        ReferralRecord.Status.CONNECTED,
        ReferralRecord.Status.FOLLOW_UP,
        ReferralRecord.Status.CANCELLED,
    },
    ReferralRecord.Status.CONNECTED: {
        ReferralRecord.Status.COMPLETED,
        ReferralRecord.Status.FOLLOW_UP,
        ReferralRecord.Status.CANCELLED,
    },
    ReferralRecord.Status.FOLLOW_UP: {
        ReferralRecord.Status.SHARED,
        ReferralRecord.Status.ACCEPTED,
        ReferralRecord.Status.CONNECTED,
        ReferralRecord.Status.COMPLETED,
        ReferralRecord.Status.CANCELLED,
    },
    ReferralRecord.Status.COMPLETED: set(),
    ReferralRecord.Status.CANCELLED: set(),
}



def manageable_providers(user):
    if user.is_superuser:
        return ServiceProvider.objects.all()
    return ServiceProvider.objects.filter(
        organization__in=accessible_organizations(user)
    )


def accessible_referrals(user):
    if user.is_superuser:
        return ReferralRecord.objects.all()
    return ReferralRecord.objects.filter(
        organization__in=accessible_organizations(user)
    )


@login_required
def provider_list(request):
    organizations = accessible_organizations(request.user)

    if request.user.is_superuser:
        providers = ServiceProvider.objects.all()
    elif (
        request.user.has_perm("referrals.manage_serviceproviders")
        or request.user.has_perm("referrals.verify_serviceprovider")
    ):
        providers = manageable_providers(request.user) | ServiceProvider.objects.filter(
            is_shared=True,
            is_active=True,
            verification_status=ServiceProvider.VerificationStatus.VERIFIED,
        )
    else:
        providers = ServiceProvider.objects.filter(
            is_active=True,
            verification_status=ServiceProvider.VerificationStatus.VERIFIED,
        ).filter(
            Q(organization__in=organizations) | Q(is_shared=True)
        )

    providers = providers.distinct()

    query = request.GET.get("q", "").strip()
    if query:
        providers = providers.filter(
            Q(name__icontains=query)
            | Q(district__icontains=query)
            | Q(address__icontains=query)
            | Q(description__icontains=query)
        )

    return render(
        request,
        "referrals/provider_list.html",
        {"providers": providers, "search_query": query},
    )


@permission_required("referrals.manage_serviceproviders", raise_exception=True)
def provider_create(request):
    if request.method == "POST":
        form = ServiceProviderForm(
            request.POST,
            organizations=accessible_organizations(request.user),
        )
        if form.is_valid():
            provider = form.save(commit=False)
            provider.created_by = request.user
            provider.full_clean()
            provider.verification_status = ServiceProvider.VerificationStatus.PENDING
            provider.verified_by = None
            provider.last_verified = None
            provider.save()
            messages.success(
                request,
                "Provider saved. A different staff member must verify it.",
            )
            return redirect("provider-list")
    else:
        form = ServiceProviderForm(
            organizations=accessible_organizations(request.user),
        )

    return render(
        request,
        "referrals/provider_form.html",
        {"form": form, "page_title": "Add Service Provider"},
    )


@permission_required("referrals.manage_serviceproviders", raise_exception=True)
def provider_update(request, pk):
    provider = get_object_or_404(
        manageable_providers(request.user), pk=pk
    )

    if request.method == "POST":
        form = ServiceProviderForm(
            request.POST,
            instance=provider,
            organizations=accessible_organizations(request.user),
        )
        if form.is_valid():
            updated = form.save(commit=False)
            # Editing provider details invalidates the previous verification.
            updated.verification_status = ServiceProvider.VerificationStatus.PENDING
            updated.last_verified = None
            updated.verified_by = None
            updated.verification_notes = ""
            updated.is_shared = False
            updated.full_clean()
            updated.save()
            messages.success(
                request,
                "Provider details updated. Independent verification is required again.",
            )
            return redirect("provider-list")
    else:
        form = ServiceProviderForm(
            instance=provider,
            organizations=accessible_organizations(request.user),
        )

    return render(
        request,
        "referrals/provider_form.html",
        {"form": form, "page_title": "Edit Service Provider", "provider": provider},
    )


@permission_required("referrals.verify_serviceprovider", raise_exception=True)
@require_POST
def provider_verify(request, pk):
    provider = get_object_or_404(
        manageable_providers(request.user), pk=pk
    )

    if provider.created_by_id == request.user.id:
        messages.error(request, "A different staff member must review this provider.")
        return redirect("provider-list")

    action = request.POST.get("action")
    notes = request.POST.get("verification_notes", "").strip()

    if action == "verify":
        provider.verification_status = ServiceProvider.VerificationStatus.VERIFIED
        provider.last_verified = date.today()
        provider.verified_by = request.user
        provider.verification_notes = notes
        provider.full_clean()
        provider.save()
        messages.success(request, "Provider verified and added to the trusted directory.")
    elif action == "needs_review":
        provider.verification_status = ServiceProvider.VerificationStatus.NEEDS_REVIEW
        provider.verified_by = request.user
        provider.verification_notes = notes
        provider.last_verified = None
        provider.is_shared = False
        provider.full_clean()
        provider.save()
        messages.info(request, "Provider marked for further verification.")
    elif action == "reject":
        provider.verification_status = ServiceProvider.VerificationStatus.REJECTED
        provider.verified_by = request.user
        provider.verification_notes = notes
        provider.last_verified = None
        provider.is_shared = False
        provider.full_clean()
        provider.save()
        messages.warning(request, "Provider was not approved.")
    else:
        messages.error(request, "Invalid provider review action.")

    return redirect("provider-list")


@permission_required("referrals.manage_referrals", raise_exception=True)
def referral_list(request):
    records = accessible_referrals(request.user).select_related(
        "provider", "referring_staff", "assigned_staff"
    )

    query = request.GET.get("q", "").strip()
    if query:
        records = records.filter(
            Q(reference_code__icontains=query)
            | Q(provider__name__icontains=query)
        )

    status = request.GET.get("status", "").strip()
    if status:
        records = records.filter(status=status)

    return render(
        request,
        "referrals/referral_list.html",
        {
            "records": records,
            "search_query": query,
            "selected_status": status,
            "status_choices": ReferralRecord.Status.choices,
        },
    )


@login_required
@login_required
@login_required
@login_required
@permission_required("referrals.manage_referrals", raise_exception=True)
def referral_follow_up_list(request):
    """Show open referrals requiring follow-up attention."""

    today = timezone.localdate()

    active_statuses = [
        ReferralRecord.Status.NEW,
        ReferralRecord.Status.SHARED,
        ReferralRecord.Status.ACCEPTED,
        ReferralRecord.Status.CONNECTED,
        ReferralRecord.Status.FOLLOW_UP,
    ]

    open_records = accessible_referrals(request.user).filter(
        status__in=active_statuses
    ).select_related(
        "organization",
        "provider",
        "assigned_staff",
        "referring_staff",
    ).order_by("follow_up_due", "-created_at")

    sections = [
        {
            "title": "Overdue Follow-ups",
            "description": "Open referrals whose follow-up dates have passed.",
            "records": open_records.filter(follow_up_due__lt=today),
        },
        {
            "title": "Due Today",
            "description": "Open referrals scheduled for follow-up today.",
            "records": open_records.filter(follow_up_due=today),
        },
        {
            "title": "Upcoming Follow-ups",
            "description": "Open referrals with future follow-up dates.",
            "records": open_records.filter(follow_up_due__gt=today),
        },
        {
            "title": "Unassigned Referrals",
            "description": "Open referrals without an assigned staff member.",
            "records": open_records.filter(assigned_staff__isnull=True),
        },
        {
            "title": "Unscheduled Follow-ups",
            "description": "Open referrals without a follow-up date.",
            "records": open_records.filter(follow_up_due__isnull=True),
        },
    ]

    return render(
        request,
        "referrals/follow_up_list.html",
        {
            "sections": sections,
            "today": today,
        },
    )


@permission_required("referrals.manage_referrals", raise_exception=True)
@transaction.atomic
def referral_create(request):
    if request.method == "POST":
        form = ReferralRecordForm(
            request.POST,
            organizations=accessible_organizations(request.user),
        )

        if form.is_valid():
            record = form.save(commit=False)
            record.referring_staff = request.user
            record.status = ReferralRecord.Status.NEW
            record.closed_at = None
            record.full_clean()
            record.save()

            ReferralStatusHistory.objects.create(
                referral=record,
                from_status="",
                to_status=record.status,
                changed_by=request.user,
                note="Referral created",
            )

            messages.success(
                request,
                f"Referral {record.reference_code} created successfully.",
            )
            return redirect("referral-detail", pk=record.pk)
    else:
        form = ReferralRecordForm(
            organizations=accessible_organizations(request.user),
        )

    return render(
        request,
        "referrals/referral_form.html",
        {"form": form, "page_title": "Create Referral"},
    )


@permission_required("referrals.manage_referrals", raise_exception=True)
def referral_detail(request, pk):
    record = get_object_or_404(
        accessible_referrals(request.user).select_related(
            "provider", "referring_staff", "assigned_staff"
        ),
        pk=pk,
    )
    status_history = record.status_history.select_related(
        "changed_by"
    ).all()

    return render(
        request,
        "referrals/referral_detail.html",
        {
            "record": record,
            "status_history": status_history,
        },
    )


@permission_required("referrals.manage_referrals", raise_exception=True)
@transaction.atomic
def referral_update(request, pk):
    record = get_object_or_404(
        accessible_referrals(request.user).select_for_update(),
        pk=pk,
    )

    # Capture the database status before the form modifies the instance.
    original_status = record.status

    if request.method == "POST":
        form = ReferralRecordForm(
            request.POST,
            instance=record,
            organizations=accessible_organizations(request.user),
        )

        if form.is_valid():
            updated = form.save(commit=False)
            new_status = updated.status

            # Prevent skipping required workflow stages.
            if (
                new_status != original_status
                and new_status not in REFERRAL_STATUS_TRANSITIONS.get(
                    original_status, set()
                )
            ):
                status_labels = dict(ReferralRecord.Status.choices)
                allowed = REFERRAL_STATUS_TRANSITIONS.get(
                    original_status, set()
                )

                if allowed:
                    permitted = ", ".join(
                        status_labels.get(item, item)
                        for item in sorted(allowed)
                    )
                    error_message = (
                        f"This status change is not permitted. "
                        f"Allowed next statuses: {permitted}."
                    )
                else:
                    error_message = (
                        "This referral is closed and cannot be reopened "
                        "through the standard update form."
                    )

                form.add_error("status", error_message)

            else:
                updated.full_clean()

                if new_status in (
                    ReferralRecord.Status.COMPLETED,
                    ReferralRecord.Status.CANCELLED,
                ):
                    updated.closed_at = (
                        updated.closed_at or timezone.now()
                    )
                else:
                    updated.closed_at = None

                updated.save()

                # Record only genuine status changes.
                if new_status != original_status:
                    ReferralStatusHistory.objects.create(
                        referral=updated,
                        from_status=original_status,
                        to_status=new_status,
                        changed_by=request.user,
                    )

                messages.success(request, "Referral record updated.")
                return redirect("referral-detail", pk=updated.pk)

    else:
        form = ReferralRecordForm(
            instance=record,
            organizations=accessible_organizations(request.user),
        )

    return render(
        request,
        "referrals/referral_form.html",
        {"form": form, "page_title": "Update Referral", "record": record},
    )
