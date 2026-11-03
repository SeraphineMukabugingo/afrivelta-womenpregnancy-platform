from django.urls import path
from . import views

urlpatterns = [
    path("", views.programme_list, name="programme-list"),
    path("new/", views.programme_create, name="programme-create"),

    path(
        "<int:programme_pk>/activities/new/",
        views.programme_activity_create,
        name="programme-activity-create",
    ),
    path(
        "activities/<int:pk>/edit/",
        views.programme_activity_update,
        name="programme-activity-update",
    ),

    path(
        "<int:programme_pk>/milestones/new/",
        views.programme_milestone_create,
        name="programme-milestone-create",
    ),
    path(
        "milestones/<int:pk>/edit/",
        views.programme_milestone_update,
        name="programme-milestone-update",
    ),

    path("<int:pk>/edit/", views.programme_update, name="programme-update"),
    path("<int:pk>/", views.programme_detail, name="programme-detail"),
]
