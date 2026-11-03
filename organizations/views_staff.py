from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import StaffCreationForm, StaffUpdateForm
from .models import Organization, OrganizationMembership

User = get_user_model()


def staff_manager_required(view):
    return user_passes_test(
        lambda user: user.is_authenticated and (
            user.is_superuser
            or user.has_perm("organizations.manage_platform_users")
        )
    )(view)


def manageable_organizations(user):
    if user.is_superuser:
        return Organization.objects.all()

    return Organization.objects.filter(
        status=Organization.Status.ACTIVE,
        memberships__user=user,
        memberships__status=OrganizationMembership.Status.ACTIVE,
        memberships__role=OrganizationMembership.Role.ORGANIZATION_ADMIN,
    ).distinct()


def manageable_staff_users(user, organizations):
    users = User.objects.filter(
        organization_memberships__organization__in=organizations
    ).distinct()

    # Never modify superuser accounts through this staff interface.
    users = users.exclude(is_superuser=True).exclude(pk=user.pk)

    if not user.is_superuser:
        users = users.exclude(groups__name="Platform Administrator")

    return users


@staff_manager_required
def staff_list(request):
    organizations = manageable_organizations(request.user)

    if request.user.is_superuser:
        users = User.objects.all()
    else:
        users = User.objects.filter(
            organization_memberships__organization__in=organizations
        ).distinct()

    query = request.GET.get("q", "").strip()

    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    users = users.prefetch_related(
        "groups",
        "organization_memberships__organization",
    ).order_by("username")

    return render(
        request,
        "organizations/staff_list.html",
        {"staff_members": users, "search_query": query},
    )


@staff_manager_required
@transaction.atomic
def staff_create(request):
    organizations = manageable_organizations(request.user)

    form = StaffCreationForm(
        request.POST or None,
        organizations=organizations,
        allow_platform_admin=request.user.is_superuser,
    )

    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.groups.set(form.cleaned_data["roles"])

        OrganizationMembership.objects.create(
            organization=form.cleaned_data["organization"],
            user=user,
            role=form.cleaned_data["organization_role"],
            status=OrganizationMembership.Status.ACTIVE,
        )

        messages.success(
            request,
            f"Staff account {user.username} created successfully.",
        )
        return redirect("staff-list")

    return render(
        request,
        "organizations/staff_form.html",
        {"form": form},
    )


@staff_manager_required
@transaction.atomic
def staff_update(request, pk):
    organizations = manageable_organizations(request.user)

    staff_member = get_object_or_404(
        manageable_staff_users(request.user, organizations),
        pk=pk,
    )

    form = StaffUpdateForm(
        request.POST or None,
        instance=staff_member,
        organizations=organizations,
        allow_platform_admin=request.user.is_superuser,
        allow_account_control=request.user.is_superuser,
    )

    if request.method == "POST" and form.is_valid():
        staff_member = form.save()
        staff_member.groups.set(form.cleaned_data["roles"])

        membership, created = OrganizationMembership.objects.get_or_create(
            organization=form.cleaned_data["organization"],
            user=staff_member,
            defaults={
                "role": form.cleaned_data["organization_role"],
                "status": form.cleaned_data["membership_status"],
            },
        )

        if not created:
            membership.role = form.cleaned_data["organization_role"]
            membership.status = form.cleaned_data["membership_status"]
            membership.save(update_fields=["role", "status"])

        if request.user.is_superuser:
            staff_member.is_active = form.cleaned_data["account_active"]
            staff_member.save(update_fields=["is_active"])

        messages.success(
            request,
            f"Staff account {staff_member.username} updated successfully.",
        )
        return redirect("staff-list")

    return render(
        request,
        "organizations/staff_form.html",
        {
            "form": form,
            "staff_member": staff_member,
            "page_title": "Edit Staff Member",
            "button_label": "Save Changes",
        },
    )
