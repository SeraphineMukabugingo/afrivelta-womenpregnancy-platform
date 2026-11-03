from django.urls import path
from . import views

urlpatterns = [
    path("", views.provider_list, name="provider-list"),
    path("providers/new/", views.provider_create, name="provider-create"),
    path(
        "providers/<int:pk>/edit/",
        views.provider_update,
        name="provider-update",
    ),
    path(
        "providers/<int:pk>/verify/",
        views.provider_verify,
        name="provider-verify",
    ),
    path(
        "records/follow-ups/",
        views.referral_follow_up_list,
        name="referral-follow-up-list",
    ),
    path("records/", views.referral_list, name="referral-list"),
    path("records/new/", views.referral_create, name="referral-create"),
    path(
        "records/<int:pk>/",
        views.referral_detail,
        name="referral-detail",
    ),
    path(
        "records/<int:pk>/edit/",
        views.referral_update,
        name="referral-update",
    ),
]
