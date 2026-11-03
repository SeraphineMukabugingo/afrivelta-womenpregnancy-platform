from django.urls import path
from . import views_staff, views_organization_admin

urlpatterns = [
    path("organizations/", views_organization_admin.organization_list, name="organization-admin-list"),
    path("organizations/new/", views_organization_admin.organization_create, name="organization-admin-create"),
    path("organizations/<int:pk>/", views_organization_admin.organization_detail, name="organization-admin-detail"),
    path("organizations/<int:pk>/edit/", views_organization_admin.organization_update, name="organization-admin-update"),
    path("organizations/<int:pk>/review/", views_organization_admin.organization_review, name="organization-admin-review"),
    path("organizations/<int:organization_pk>/members/new/", views_organization_admin.membership_create, name="organization-membership-create"),
    path("organizations/members/<int:pk>/edit/", views_organization_admin.membership_update, name="organization-membership-update"),
    path("", views_staff.staff_list, name="staff-list"),
    path("new/", views_staff.staff_create, name="staff-create"),
    path("<int:pk>/edit/", views_staff.staff_update, name="staff-update"),
]
