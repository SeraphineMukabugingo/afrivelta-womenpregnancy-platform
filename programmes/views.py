from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from organizations.models import Organization, OrganizationMembership
from .forms import ProgrammeForm, ProgrammeActivityForm, ProgrammeMilestoneForm
from .models import Programme, ProgrammeActivity, ProgrammeMilestone


def accessible_organizations(user, can_manage=False):
    if user.is_superuser:
        return Organization.objects.all()

    memberships = OrganizationMembership.objects.filter(
        user=user,
        status=OrganizationMembership.Status.ACTIVE,
        organization__status=Organization.Status.ACTIVE,
    )

    if can_manage:
        if not user.has_perm("programmes.manage_programmes"):
            return Organization.objects.none()

        memberships = memberships.filter(
            role__in=[
                OrganizationMembership.Role.ORGANIZATION_ADMIN,
                OrganizationMembership.Role.PROGRAMME_MANAGER,
            ]
        )

    return Organization.objects.filter(
        memberships__in=memberships
    ).distinct()


@login_required
def programme_list(request):
    organizations = accessible_organizations(request.user)

    editable_ids = set(
        accessible_organizations(
            request.user, can_manage=True
        ).values_list("id", flat=True)
    )

    programmes = (
        Programme.objects
        .filter(organization__in=organizations)
        .select_related("organization", "lead_user", "created_by")
        .order_by("-created_at")
    )

    search_query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()

    if search_query:
        programmes = programmes.filter(
            Q(name__icontains=search_query)
            | Q(organization__name__icontains=search_query)
            | Q(target_group__icontains=search_query)
            | Q(district_or_city__icontains=search_query)
        )

    valid_statuses = [value for value, label in Programme.Status.choices]
    if selected_status in valid_statuses:
        programmes = programmes.filter(status=selected_status)
    else:
        selected_status = ""

    return render(
        request,
        "programmes/programme_list.html",
        {
            "programmes": programmes,
            "programme_count": programmes.count(),
            "search_query": search_query,
            "selected_status": selected_status,
            "status_choices": Programme.Status.choices,
            "editable_organization_ids": editable_ids,
        },
    )


@login_required
def programme_detail(request, pk):
    organizations = accessible_organizations(request.user)

    programme = get_object_or_404(
        Programme.objects.filter(organization__in=organizations)
        .select_related("organization", "lead_user", "created_by")
        .prefetch_related(
            "activities__assigned_to",
            "activities__created_by",
        ),
        pk=pk,
    )

    editable_ids = set(
        accessible_organizations(
            request.user, can_manage=True
        ).values_list("id", flat=True)
    )

    summary = programme.activities.aggregate(
        total=Count("id"),
        planned=Count(
            "id",
            filter=Q(status=ProgrammeActivity.Status.PLANNED),
        ),
        in_progress=Count(
            "id",
            filter=Q(status=ProgrammeActivity.Status.IN_PROGRESS),
        ),
        completed=Count(
            "id",
            filter=Q(status=ProgrammeActivity.Status.COMPLETED),
        ),
        average_progress=Avg("progress_percent"),
    )

    summary["average_progress"] = round(
        summary["average_progress"] or 0
    )

    return render(
        request,
        "programmes/programme_detail.html",
        {
            "programme": programme,
            "can_edit": programme.organization_id in editable_ids,
            "activity_summary": summary,
        },
    )


@login_required
@permission_required("programmes.manage_programmes", raise_exception=True)
def programme_create(request):
    organizations = accessible_organizations(
        request.user, can_manage=True
    )

    if request.method == "POST":
        form = ProgrammeForm(
            request.POST, organizations=organizations
        )

        if form.is_valid():
            programme = form.save(commit=False)
            programme.created_by = request.user
            programme.save()
            messages.success(request, "Programme created successfully.")
            return redirect("programme-list")
    else:
        form = ProgrammeForm(organizations=organizations)

    return render(
        request,
        "programmes/programme_form.html",
        {
            "form": form,
            "organizations_available": organizations.exists(),
            "page_title": "Create a Programme",
            "button_label": "Save Programme",
        },
    )


@login_required
@permission_required("programmes.manage_programmes", raise_exception=True)
def programme_update(request, pk):
    organizations = accessible_organizations(
        request.user, can_manage=True
    )

    programme = get_object_or_404(
        Programme.objects.filter(organization__in=organizations),
        pk=pk,
    )

    if request.method == "POST":
        form = ProgrammeForm(
            request.POST,
            instance=programme,
            organizations=organizations,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Programme updated successfully.")
            return redirect("programme-detail", pk=programme.pk)
    else:
        form = ProgrammeForm(
            instance=programme, organizations=organizations
        )

    return render(
        request,
        "programmes/programme_form.html",
        {
            "form": form,
            "organizations_available": organizations.exists(),
            "page_title": "Edit Programme",
            "button_label": "Save Changes",
        },
    )


@login_required
@permission_required("programmes.manage_programmes", raise_exception=True)
def programme_activity_create(request, programme_pk):
    organizations = accessible_organizations(
        request.user, can_manage=True
    )

    programme = get_object_or_404(
        Programme.objects.filter(organization__in=organizations),
        pk=programme_pk,
    )

    if request.method == "POST":
        form = ProgrammeActivityForm(
            request.POST, programme=programme
        )

        if form.is_valid():
            activity = form.save(commit=False)
            activity.programme = programme
            activity.created_by = request.user
            activity.save()

            messages.success(request, "Activity created successfully.")
            return redirect("programme-detail", pk=programme.pk)
    else:
        form = ProgrammeActivityForm(programme=programme)

    return render(
        request,
        "programmes/activity_form.html",
        {
            "form": form,
            "programme": programme,
            "page_title": "Add Programme Activity",
            "button_label": "Save Activity",
        },
    )


@login_required
@permission_required("programmes.manage_programmes", raise_exception=True)
def programme_activity_update(request, pk):
    organizations = accessible_organizations(
        request.user, can_manage=True
    )

    activity = get_object_or_404(
        ProgrammeActivity.objects
        .filter(programme__organization__in=organizations)
        .select_related("programme", "programme__organization"),
        pk=pk,
    )

    programme = activity.programme

    if request.method == "POST":
        form = ProgrammeActivityForm(
            request.POST,
            instance=activity,
            programme=programme,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Activity updated successfully.")
            return redirect("programme-detail", pk=programme.pk)
    else:
        form = ProgrammeActivityForm(
            instance=activity, programme=programme
        )

    return render(
        request,
        "programmes/activity_form.html",
        {
            "form": form,
            "programme": programme,
            "page_title": "Update Programme Activity",
            "button_label": "Save Changes",
        },
    )


@login_required
@permission_required("programmes.manage_programmes", raise_exception=True)
def programme_milestone_create(request, programme_pk):
    organizations = accessible_organizations(
        request.user, can_manage=True
    )

    programme = get_object_or_404(
        Programme.objects.filter(organization__in=organizations),
        pk=programme_pk,
    )

    if request.method == "POST":
        form = ProgrammeMilestoneForm(
            request.POST, programme=programme
        )
        if form.is_valid():
            milestone = form.save(commit=False)
            milestone.programme = programme
            milestone.created_by = request.user
            milestone.save()

            messages.success(request, "Milestone created successfully.")
            return redirect("programme-detail", pk=programme.pk)
    else:
        form = ProgrammeMilestoneForm(programme=programme)

    return render(
        request,
        "programmes/milestone_form.html",
        {
            "form": form,
            "programme": programme,
            "page_title": "Add Programme Milestone",
            "button_label": "Save Milestone",
        },
    )


@login_required
@permission_required("programmes.manage_programmes", raise_exception=True)
def programme_milestone_update(request, pk):
    organizations = accessible_organizations(
        request.user, can_manage=True
    )

    milestone = get_object_or_404(
        ProgrammeMilestone.objects.filter(
            programme__organization__in=organizations
        ).select_related("programme", "programme__organization"),
        pk=pk,
    )

    programme = milestone.programme

    if request.method == "POST":
        form = ProgrammeMilestoneForm(
            request.POST,
            instance=milestone,
            programme=programme,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Milestone updated successfully.")
            return redirect("programme-detail", pk=programme.pk)
    else:
        form = ProgrammeMilestoneForm(
            instance=milestone, programme=programme
        )

    return render(
        request,
        "programmes/milestone_form.html",
        {
            "form": form,
            "programme": programme,
            "page_title": "Edit Programme Milestone",
            "button_label": "Save Changes",
        },
    )
