from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Organization, OrganizationMembership


@login_required
def dashboard(request):
    """Render the organisation dashboard using authorised organisation data."""

    if request.user.is_superuser:
        organizations = Organization.objects.all()
        memberships = OrganizationMembership.objects.select_related(
            "organization", "user"
        )
    else:
        memberships = OrganizationMembership.objects.filter(
            user=request.user,
            status=OrganizationMembership.Status.ACTIVE,
            organization__status=Organization.Status.ACTIVE,
        ).select_related("organization", "user")

        organizations = Organization.objects.filter(
            memberships__in=memberships
        ).distinct()

    organizations = organizations.order_by("name")

    modules = [
        {
            "number": "01",
            "title": "Prevention Programme Planning",
            "description": (
                "Create programmes, define objectives, assign staff, "
                "schedule activities and track progress."
            ),
            "status": "Planned",
        },
        {
            "number": "02",
            "title": "Youth Education & Reviewed AI Guidance",
            "description": (
                "Provide age-appropriate reproductive-health information "
                "based on reviewed and trusted sources."
            ),
            "status": "Planned",
        },
        {
            "number": "03",
            "title": "Verified Health-Service Referrals",
            "description": (
                "Maintain an approved directory of health and support "
                "services with verification and review dates."
            ),
            "status": "Planned",
        },
        {
            "number": "04",
            "title": "Impact Measurement & Funder Reports",
            "description": (
                "Monitor programme delivery, aggregate indicators, "
                "learning outcomes and service connections."
            ),
            "status": "Planned",
        },
    ]

    context = {
        "organizations": organizations,
        "organization_count": organizations.count(),
        "active_organization_count": organizations.filter(
            status=Organization.Status.ACTIVE
        ).count(),
        "pending_organization_count": organizations.filter(
            status=Organization.Status.PENDING_REVIEW
        ).count(),
        "membership_count": memberships.count(),
        "modules": modules,
    }

    return render(
        request,
        "organizations/dashboard.html",
        context,
    )


@login_required
def module_placeholder(request, module_key):
    module_pages = {
        "youth-education": {
            "title": "Youth Education & Reviewed AI Guidance",
            "description": (
                "Age-appropriate reproductive-health education and "
                "carefully reviewed guidance from trusted sources."
            ),
            "features": [
                "Organised, age-appropriate learning materials",
                "Content review and approval workflow",
                "English and Kinyarwanda content planning",
                "Clear safeguarding and escalation guidance",
            ],
        },
        "verified-referrals": {
            "title": "Verified Health-Service Referrals",
            "description": (
                "A directory of reviewed health and support providers "
                "to help participating organisations connect young people "
                "with appropriate services."
            ),
            "features": [
                "Health-provider and service directory",
                "Provider verification and review dates",
                "Service location and contact information",
                "Referral records designed with privacy safeguards",
            ],
        },
        "impact-reporting": {
            "title": "Impact Measurement & Funder Reports",
            "description": (
                "Programme indicators, documented results and "
                "evidence-based reporting for organisations and funders."
            ),
            "features": [
                "Programme indicators, baselines and targets",
                "Periodic results and progress comparisons",
                "Activity and milestone summaries",
                "Professional programme and funder reports",
            ],
        },
    }

    module = module_pages.get(module_key)
    if module is None:
        raise Http404("Module not found.")

    module["status"] = "Planned — Under Development"

    return render(
        request,
        "organizations/module_placeholder.html",
        {"module": module},
    )
