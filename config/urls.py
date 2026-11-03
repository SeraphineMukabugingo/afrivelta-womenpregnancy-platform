from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from organizations.views import dashboard, module_placeholder


urlpatterns = [
    path("admin/", admin.site.urls),

    path(
        "accounts/login/",
        LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        LogoutView.as_view(next_page="login"),
        name="logout",
    ),

    path("staff/", include("organizations.urls")),
    path("programmes/", include("programmes.urls")),
    path("education/", include("content_library.urls")),
    path("referrals/", include("referrals.urls")),
    path("modules/impact-reporting/", include("reporting.urls")),

    path(
        "modules/<slug:module_key>/",
        module_placeholder,
        name="module-placeholder",
    ),

    path("", dashboard, name="dashboard"),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
