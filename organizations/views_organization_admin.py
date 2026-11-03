from django.contrib import messages
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms_organization_admin import (
    OrganizationAdminForm,
    MembershipCreateForm,
    MembershipUpdateForm,
)
from .models import Organization, OrganizationMembership


def organization_admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or request.user.has_perm(
                "organizations.manage_organization_members"
            )
        ):
            raise PermissionDenied

        return view(request, *args, **kwargs)

    return wrapped


@organization_admin_required
def organization_list(request):
    organizations = Organization.objects.prefetch_related("memberships")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if query:
        organizations = organizations.filter(name__icontains=query)

    valid_statuses = [value for value, label in Organization.Status.choices]
    if status in valid_statuses:
        organizations = organizations.filter(status=status)
    else:
        status = ""

    return render(
        request,
        "organizations/organization_list.html",
        {
            "organizations": organizations,
            "search_query": query,
            "selected_status": status,
            "status_choices": Organization.Status.choices,
        },
    )


@organization_admin_required
def organization_create(request):
    form = OrganizationAdminForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        organization = form.save(commit=False)
        organization.status = Organization.Status.PENDING_REVIEW
        organization.reviewed_by = None
        organization.reviewed_at = None
        organization.save()

        messages.success(
            request,
            "Organization registered and placed in the review queue.",
        )
        return redirect("organization-admin-detail", pk=organization.pk)

    return render(
        request,
        "organizations/organization_form.html",
        {"form": form, "page_title": "Register Organization"},
    )


@organization_admin_required
def organization_detail(request, pk):
    organization = get_object_or_404(Organization, pk=pk)
    memberships = organization.memberships.select_related("user").order_by(
        "user__username"
    )

    return render(
        request,
        "organizations/organization_detail.html",
        {
            "organization": organization,
            "memberships": memberships,
            "active_count": memberships.filter(
                status=OrganizationMembership.Status.ACTIVE
            ).count(),
            "invited_count": memberships.filter(
                status=OrganizationMembership.Status.INVITED
            ).count(),
            "suspended_count": memberships.filter(
                status=OrganizationMembership.Status.SUSPENDED
            ).count(),
        },
    )


@organization_admin_required
def organization_update(request, pk):
    organization = get_object_or_404(Organization, pk=pk)
    form = OrganizationAdminForm(
        request.POST or None,
        instance=organization,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Organization details updated.")
        return redirect("organization-admin-detail", pk=pk)

    return render(
        request,
        "organizations/organization_form.html",
        {
            "form": form,
            "organization": organization,
            "page_title": "Edit Organization",
        },
    )


@organization_admin_required
@require_POST
@transaction.atomic
def organization_review(request, pk):
    organization = get_object_or_404(
        Organization.objects.select_for_update(),
        pk=pk,
    )
    action = request.POST.get("action")
    notes = request.POST.get("review_notes", "").strip()

    transitions = {
        "approve": (
            Organization.Status.PENDING_REVIEW,
            Organization.Status.ACTIVE,
            "Organization approved.",
        ),
        "reject": (
            Organization.Status.PENDING_REVIEW,
            Organization.Status.REJECTED,
            "Organization rejected.",
        ),
        "suspend": (
            Organization.Status.ACTIVE,
            Organization.Status.SUSPENDED,
            "Organization suspended.",
        ),
        "reactivate": (
            Organization.Status.SUSPENDED,
            Organization.Status.ACTIVE,
            "Organization reactivated. Memberships remain suspended.",
        ),
        "reopen": (
            Organization.Status.REJECTED,
            Organization.Status.PENDING_REVIEW,
            "Organization returned to pending review.",
        ),
    }

    transition = transitions.get(action)

    if not transition or organization.status != transition[0]:
        messages.error(request, "This organization action is not permitted.")
        return redirect("organization-admin-detail", pk=pk)

    organization.status = transition[1]
    organization.review_notes = notes
    organization.reviewed_by = request.user
    organization.reviewed_at = timezone.now()
    organization.save(
        update_fields=[
            "status", "review_notes", "reviewed_by",
            "reviewed_at", "updated_at",
        ]
    )

    if action == "suspend":
        OrganizationMembership.objects.filter(
            organization=organization,
            status=OrganizationMembership.Status.ACTIVE,
        ).update(status=OrganizationMembership.Status.SUSPENDED)

    messages.success(request, transition[2])
    return redirect("organization-admin-detail", pk=pk)


@organization_admin_required
def membership_create(request, organization_pk):
    organization = get_object_or_404(Organization, pk=organization_pk)
    form = MembershipCreateForm(
        request.POST or None,
        organization=organization,
    )

    if request.method == "POST" and form.is_valid():
        membership = form.save(commit=False)
        membership.organization = organization
        membership.save()

        messages.success(request, "Organization membership created.")
        return redirect("organization-admin-detail", pk=organization.pk)

    return render(
        request,
        "organizations/membership_form.html",
        {
            "form": form,
            "organization": organization,
            "page_title": "Add Organization Member",
        },
    )


@organization_admin_required
def membership_update(request, pk):
    membership = get_object_or_404(
        OrganizationMembership.objects.select_related(
            "organization", "user"
        ),
        pk=pk,
    )
    form = MembershipUpdateForm(
        request.POST or None,
        instance=membership,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Organization membership updated.")
        return redirect(
            "organization-admin-detail",
            pk=membership.organization_id,
        )

    return render(
        request,
        "organizations/membership_form.html",
        {
            "form": form,
            "organization": membership.organization,
            "membership": membership,
            "page_title": "Update Organization Membership",
        },
    )
