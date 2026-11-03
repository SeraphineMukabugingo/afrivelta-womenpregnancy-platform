from .models import Organization, OrganizationMembership


def accessible_organizations(user):
    """Return organizations available to an authenticated user."""
    if not user.is_authenticated:
        return Organization.objects.none()

    if user.is_superuser:
        return Organization.objects.all()

    return Organization.objects.filter(
        status=Organization.Status.ACTIVE,
        memberships__user=user,
        memberships__status=OrganizationMembership.Status.ACTIVE,
    ).distinct()


def has_active_membership(user, organization):
    if user.is_superuser:
        return True

    return OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        status=OrganizationMembership.Status.ACTIVE,
        organization__status=Organization.Status.ACTIVE,
    ).exists()


def has_organization_role(user, organization, roles):
    if user.is_superuser:
        return True

    return OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        status=OrganizationMembership.Status.ACTIVE,
        organization__status=Organization.Status.ACTIVE,
        role__in=roles,
    ).exists()
