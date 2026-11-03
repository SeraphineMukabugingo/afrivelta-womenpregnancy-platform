from django.urls import path
from . import views

urlpatterns = [
    path("", views.content_list, name="content-library-list"),
    path("new/", views.content_create, name="content-create"),
    path("<int:pk>/", views.content_detail, name="content-library-detail"),
    path("<int:pk>/edit/", views.content_update, name="content-update"),
    path(
        "<int:pk>/sources/new/",
        views.content_source_create,
        name="content-source-create",
    ),
    path(
        "<int:pk>/submit/",
        views.content_submit_for_review,
        name="content-submit-review",
    ),
    path(
        "<int:pk>/review/",
        views.content_review,
        name="content-review",
    ),
    path(
        "<int:pk>/publish/",
        views.content_publish,
        name="content-publish",
    ),
]
