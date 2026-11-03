from django.urls import path

from . import views

urlpatterns = [
    path("", views.impact_dashboard, name="reporting-dashboard"),
    path("quarterly/", views.quarterly_impact_report, name="reporting-quarterly"),
    path("export.csv", views.export_impact_csv, name="reporting-export"),
]
