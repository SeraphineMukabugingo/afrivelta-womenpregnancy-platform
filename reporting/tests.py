from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from organizations.models import Organization, OrganizationMembership
from programmes.models import Programme, ProgrammeMilestone
from content_library.models import ContentItem
from referrals.models import ServiceProvider, ReferralRecord

from .services import build_reporting_data
from .views import get_reporting_period, shift_month


User = get_user_model()


class ReportingTestBase(TestCase):

    def setUp(self):
        self.today = timezone.localdate()

        self.org_a = Organization.objects.create(
            name="Test Organization A",
            organization_type="ngo",
            country="Rwanda",
            status="active",
        )

        self.org_b = Organization.objects.create(
            name="Test Organization B",
            organization_type="ngo",
            country="Rwanda",
            status="active",
        )

        self.analyst = User.objects.create_user(
            username="reporting_analyst",
            password="Test-Password-123!",
        )

        self.add_group_permissions(
            self.analyst,
            "Reporting Test Analyst",
            [
                ("programmes", "view_programme_analytics"),
                ("referrals", "view_referral_metrics"),
            ],
        )

        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.analyst,
            role="staff",
            status="active",
        )

        self.analyst = User.objects.get(pk=self.analyst.pk)

    def add_group_permissions(self, user, group_name, permissions):
        group = Group.objects.create(name=group_name)

        for app_label, codename in permissions:
            permission = Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )
            group.permissions.add(permission)

        user.groups.add(group)

    def create_programme(self, organization, name):
        return Programme.objects.create(
            organization=organization,
            name=name,
            objectives="Improve access to appropriate health education.",
            target_group="Young people",
            start_date=self.today,
            end_date=self.today + timedelta(days=90),
        )

    def create_provider(self, organization, user):
        return ServiceProvider.objects.create(
            organization=organization,
            name=f"Test Provider {organization.pk}",
            category="maternal",
            description="Test healthcare service.",
            address="Kigali",
            district="Gasabo",
            verification_status="verified",
            last_verified=self.today,
            verified_by=user,
            created_by=user,
        )

    def create_referral(self, organization, user):
        provider = self.create_provider(organization, user)

        return ReferralRecord.objects.create(
            organization=organization,
            provider=provider,
            referring_staff=user,
            consent_confirmed=True,
            status="new",
            follow_up_due=self.today + timedelta(days=7),
            non_identifying_notes="Test referral record.",
        )

    def create_content(self, organization, title):
        return ContentItem.objects.create(
            organization=organization,
            title=title,
            body="Test educational content.",
        )


class ReportingIsolationTests(ReportingTestBase):

    def test_analyst_only_sees_authorized_organization_data(self):
        self.create_programme(self.org_a, "Organization A Programme")
        self.create_programme(self.org_b, "Organization B Programme")

        self.create_referral(self.org_a, self.analyst)
        self.create_referral(self.org_b, self.analyst)

        report = build_reporting_data(self.analyst)

        self.assertEqual(report["organization_scope_count"], 1)
        self.assertEqual(report["programme"]["total"], 1)
        self.assertEqual(report["referrals"]["total"], 1)
        self.assertEqual(report["providers"]["total"], 1)

    def test_education_reviewer_only_sees_own_organization_content(self):
        reviewer = User.objects.create_user(
            username="reporting_reviewer",
            password="Test-Password-123!",
        )

        self.add_group_permissions(
            reviewer,
            "Reporting Test Education Reviewer",
            [("content_library", "review_content")],
        )

        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=reviewer,
            role="staff",
            status="active",
        )

        reviewer = User.objects.get(pk=reviewer.pk)

        self.create_content(self.org_a, "Organization A Content")
        self.create_content(self.org_b, "Organization B Content")
        self.create_content(None, "Unassigned Legacy Content")

        report = build_reporting_data(reviewer)

        self.assertEqual(report["education"]["total"], 1)
        self.assertEqual(report["education"]["unassigned"], 0)

    def test_platform_superuser_can_see_unassigned_legacy_content(self):
        superuser = User.objects.create_superuser(
            username="reporting_superuser",
            email="superuser@example.test",
            password="Test-Password-123!",
        )

        self.create_content(None, "Unassigned Legacy Content")

        report = build_reporting_data(superuser)

        self.assertEqual(report["education"]["total"], 1)
        self.assertEqual(report["education"]["unassigned"], 1)
        self.assertTrue(report["permissions"]["access"])


class ReportingCalculationTests(ReportingTestBase):

    def test_date_filter_excludes_old_programmes(self):
        old_programme = self.create_programme(
            self.org_a, "Older Programme"
        )
        recent_programme = self.create_programme(
            self.org_a, "Recent Programme"
        )

        current_timezone = timezone.get_current_timezone()

        old_timestamp = timezone.make_aware(
            datetime.combine(
                self.today - timedelta(days=10),
                time(12, 0),
            ),
            current_timezone,
        )

        recent_timestamp = timezone.make_aware(
            datetime.combine(
                self.today - timedelta(days=1),
                time(12, 0),
            ),
            current_timezone,
        )

        Programme.objects.filter(pk=old_programme.pk).update(
            created_at=old_timestamp
        )

        Programme.objects.filter(pk=recent_programme.pk).update(
            created_at=recent_timestamp
        )

        report = build_reporting_data(
            self.analyst,
            start_date=self.today - timedelta(days=2),
            end_date=self.today,
        )

        self.assertEqual(report["programme"]["total"], 1)

    def test_unassigned_content_is_not_visible_to_ordinary_reviewer(self):
        reviewer = User.objects.create_user(
            username="content_visibility_reviewer",
            password="Test-Password-123!",
        )

        self.add_group_permissions(
            reviewer,
            "Reporting Content Reviewer",
            [("content_library", "review_content")],
        )

        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=reviewer,
            role="staff",
            status="active",
        )

        reviewer = User.objects.get(pk=reviewer.pk)

        self.create_content(None, "Private Legacy Draft")

        report = build_reporting_data(reviewer)

        self.assertEqual(report["education"]["total"], 0)


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class ReportingAccessTests(ReportingTestBase):

    def test_anonymous_user_is_redirected(self):
        client = Client(HTTP_HOST="127.0.0.1")

        response = client.get(
            reverse("reporting-dashboard")
        )

        self.assertEqual(response.status_code, 302)

    def test_general_staff_cannot_access_dashboard_or_export(self):
        staff = User.objects.create_user(
            username="reporting_general_staff",
            password="Test-Password-123!",
        )

        Group.objects.create(name="Reporting General Staff").user_set.add(
            staff
        )

        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(staff)

        dashboard = client.get(
            reverse("reporting-dashboard")
        )

        export = client.get(
            reverse("reporting-export")
        )

        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(export.status_code, 403)

    def test_authorized_analyst_can_access_dashboard(self):
        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(self.analyst)

        response = client.get(
            reverse("reporting-dashboard")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Impact & Analytics")

    def test_csv_export_contains_aggregate_metrics_only(self):
        self.create_programme(
            self.org_a, "Organization A Private Programme"
        )

        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(self.analyst)

        response = client.get(
            reverse("reporting-export")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertContains(
            response,
            "Total programmes",
        )

        csv_content = response.content.decode("utf-8")

        self.assertNotIn("Organization A Private Programme", csv_content)
        self.assertNotIn("Test referral record.", csv_content)
        self.assertNotIn("reference_code", csv_content)


class ReportingPeriodCalculationTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.today = timezone.localdate()

    def get_period(self, period, **params):
        request = self.factory.get(
            "/modules/impact-reporting/",
            {"period": period, **params},
        )
        return get_reporting_period(request)

    def test_all_records_has_no_date_limits(self):
        start, end, error = self.get_period("all")
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertIsNone(error)

    def test_current_and_previous_month_boundaries(self):
        start, end, error = self.get_period("this_month")
        self.assertEqual(start, self.today.replace(day=1))
        self.assertEqual(end, self.today)
        self.assertIsNone(error)

        start, end, error = self.get_period("last_month")
        previous_month_end = self.today.replace(day=1) - timedelta(days=1)

        self.assertEqual(start, previous_month_end.replace(day=1))
        self.assertEqual(end, previous_month_end)
        self.assertIsNone(error)

    def test_current_and_previous_quarter_boundaries(self):
        month = ((self.today.month - 1) // 3) * 3 + 1
        quarter_start = date(self.today.year, month, 1)

        start, end, error = self.get_period("this_quarter")
        self.assertEqual(start, quarter_start)
        self.assertEqual(end, self.today)
        self.assertIsNone(error)

        previous_end = quarter_start - timedelta(days=1)
        previous_month = ((previous_end.month - 1) // 3) * 3 + 1

        expected_start = date(
            previous_end.year, previous_month, 1
        )

        start, end, error = self.get_period("last_quarter")
        self.assertEqual(start, expected_start)
        self.assertEqual(end, previous_end)
        self.assertIsNone(error)

    def test_year_to_date_and_last_twelve_months(self):
        start, end, error = self.get_period("year_to_date")
        self.assertEqual(start, date(self.today.year, 1, 1))
        self.assertEqual(end, self.today)
        self.assertIsNone(error)

        start, end, error = self.get_period("last_12_months")
        self.assertEqual(
            start,
            shift_month(self.today.replace(day=1), -11),
        )
        self.assertEqual(end, self.today)
        self.assertIsNone(error)

    def test_custom_date_range(self):
        start, end, error = self.get_period(
            "custom",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 31))
        self.assertIsNone(error)

    def test_invalid_and_reversed_custom_dates(self):
        start, end, error = self.get_period(
            "custom",
            start_date="invalid-date",
        )
        self.assertEqual(error, "Invalid start date.")

        start, end, error = self.get_period(
            "custom",
            start_date="2026-11-20",
            end_date="2026-11-01",
        )
        self.assertEqual(
            error,
            "Start date must not be after end date.",
        )

    def test_unknown_period_is_rejected(self):
        start, end, error = self.get_period("unknown_period")
        self.assertEqual(error, "Invalid reporting period.")


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class ReportingPeriodHTTPTests(ReportingTestBase):

    def test_all_supported_periods_work_for_dashboard_and_csv(self):
        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(self.analyst)

        periods = [
            "all",
            "this_month",
            "last_month",
            "this_quarter",
            "last_quarter",
            "year_to_date",
            "last_12_months",
        ]

        for period in periods:
            with self.subTest(period=period):
                dashboard = client.get(
                    reverse("reporting-dashboard"),
                    {"period": period},
                )
                self.assertEqual(dashboard.status_code, 200)

                export = client.get(
                    reverse("reporting-export"),
                    {"period": period},
                )
                self.assertEqual(export.status_code, 200)
                self.assertIn("text/csv", export["Content-Type"])


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class ReportingTrendTests(ReportingTestBase):

    def test_csv_export_contains_monthly_and_quarterly_trends(self):
        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(self.analyst)

        response = client.get(
            reverse("reporting-export"),
            {"period": "this_quarter"},
        )

        self.assertEqual(response.status_code, 200)

        csv_text = response.content.decode("utf-8")

        self.assertIn("Monthly performance trends", csv_text)
        self.assertIn("Quarterly performance trends", csv_text)
        self.assertIn("Programmes created", csv_text)

    def test_new_programme_appears_in_correct_month_and_quarter(self):
        self.create_programme(
            self.org_a,
            "Trend Test Programme",
        )

        report = build_reporting_data(self.analyst)

        metrics = report["trends"]["metrics"]
        programme_index = next(
            index
            for index, metric in enumerate(metrics)
            if metric["key"] == "programmes_created"
        )

        current_month = self.today.strftime("%b %Y")
        current_quarter = (
            f"Q{((self.today.month - 1) // 3) + 1} "
            f"{self.today.year}"
        )

        monthly_row = next(
            row for row in report["trends"]["monthly"]
            if row["period_label"] == current_month
        )

        quarterly_row = next(
            row for row in report["trends"]["quarterly"]
            if row["period_label"] == current_quarter
        )

        self.assertEqual(monthly_row["values"][programme_index], 1)
        self.assertEqual(quarterly_row["values"][programme_index], 1)


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class QuarterlyImpactReportTests(ReportingTestBase):

    def setUp(self):
        super().setUp()
        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.analyst)
        self.url = reverse("reporting-quarterly")

    def test_default_report_uses_previous_completed_quarter(self):
        today = self.today
        current_quarter_month = ((today.month - 1) // 3) * 3 + 1
        current_quarter_start = date(
            today.year, current_quarter_month, 1
        )

        previous_end = current_quarter_start - timedelta(days=1)
        previous_month = ((previous_end.month - 1) // 3) * 3 + 1
        previous_start = date(
            previous_end.year, previous_month, 1
        )

        quarter_number = ((previous_start.month - 1) // 3) + 1
        expected_label = (
            f"Q{quarter_number} {previous_start.year} "
            f"({previous_start:%d %b} – {previous_end:%d %b %Y})"
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period_label"], expected_label)
        self.assertContains(response, "Quarterly Impact Report")
        self.assertContains(response, "Executive Summary")

    def test_current_quarter_report(self):
        response = self.client.get(
            self.url,
            {"period": "this_quarter"},
        )

        self.assertEqual(response.status_code, 200)

        quarter_number = ((self.today.month - 1) // 3) + 1
        expected_prefix = f"Q{quarter_number} {self.today.year}"

        self.assertTrue(
            response.context["period_label"].startswith(expected_prefix)
        )

    def test_custom_date_report(self):
        response = self.client.get(
            self.url,
            {
                "period": "custom",
                "start_date": "2026-01-05",
                "end_date": "2026-02-15",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["period_label"],
            "Q1 2026 (05 Jan – 15 Feb 2026)",
        )

    def test_invalid_quarterly_period_is_rejected(self):
        response = self.client.get(
            self.url,
            {"period": "last_12_months"},
        )

        self.assertEqual(response.status_code, 400)

    def test_reversed_custom_dates_are_rejected(self):
        response = self.client.get(
            self.url,
            {
                "period": "custom",
                "start_date": "2026-11-20",
                "end_date": "2026-11-01",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_anonymous_user_is_redirected(self):
        client = Client(HTTP_HOST="127.0.0.1")
        response = client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_general_staff_cannot_access_quarterly_report(self):
        staff = User.objects.create_user(
            username="quarterly_general_staff",
            password="Test-Password-123!",
        )

        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(staff)

        response = client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_analyst_sees_only_permitted_report_sections(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Programme implementation")
        self.assertContains(response, "Referral performance")
        self.assertNotContains(response, "Organization portfolio")
        self.assertNotContains(response, "Education and content")


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class MilestoneEvidenceReportingTests(ReportingTestBase):

    def create_milestone(self, organization, title, summary, reference):
        programme = self.create_programme(
            organization,
            f"Programme for {title}",
        )

        return ProgrammeMilestone.objects.create(
            programme=programme,
            title=title,
            due_date=self.today + timedelta(days=30),
            evidence_summary=summary,
            evidence_reference=reference,
        )

    def test_only_authorized_organization_evidence_is_reported(self):
        self.create_milestone(
            self.org_a,
            "Organization A Milestone",
            "Non-identifying evidence from Organization A.",
            "A-EVIDENCE-001",
        )

        self.create_milestone(
            self.org_b,
            "Organization B Milestone",
            "Private evidence belonging to Organization B.",
            "B-EVIDENCE-001",
        )

        report = build_reporting_data(self.analyst)

        evidence = report["programme"]["milestone_evidence_items"]

        self.assertEqual(len(evidence), 1)
        self.assertEqual(
            evidence[0]["evidence_reference"],
            "A-EVIDENCE-001",
        )
        self.assertNotIn(
            "B-EVIDENCE-001",
            [item["evidence_reference"] for item in evidence],
        )

    def test_instructional_placeholder_is_not_reported_as_evidence(self):
        self.create_milestone(
            self.org_a,
            "Pending Review Milestone",
            "Leave blank until the review has actually been completed",
            "Leave blank until an actual approval record or document reference exists",
        )

        report = build_reporting_data(self.analyst)

        self.assertEqual(
            report["programme"]["milestone_evidence_count"],
            0,
        )
        self.assertEqual(
            report["programme"]["milestone_evidence_items"],
            [],
        )

    def test_quarterly_report_does_not_expose_other_organization_evidence(self):
        self.create_milestone(
            self.org_a,
            "Authorized Milestone",
            "Evidence available to Organization A.",
            "A-QUARTERLY-001",
        )

        self.create_milestone(
            self.org_b,
            "Private Milestone",
            "Confidential evidence from Organization B.",
            "B-QUARTERLY-001",
        )

        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(self.analyst)

        response = client.get(
            reverse("reporting-quarterly"),
            {"period": "this_quarter"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A-QUARTERLY-001")
        self.assertNotContains(response, "B-QUARTERLY-001")
        self.assertNotContains(
            response,
            "Confidential evidence from Organization B.",
        )


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class QuarterlyNarrativeTests(ReportingTestBase):

    def test_report_contains_narrative_based_on_recorded_data(self):
        self.create_programme(
            self.org_a,
            "Quarterly Narrative Test Programme",
        )

        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(self.analyst)

        response = client.get(
            reverse("reporting-quarterly"),
            {"period": "this_quarter"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Executive Results Narrative")

        narrative = response.context["results_narrative"]

        self.assertTrue(
            any(
                "1 programme record(s) were created" in item
                for item in narrative
            )
        )

        self.assertTrue(
            any(
                "population health outcomes" in item
                for item in narrative
            )
        )
