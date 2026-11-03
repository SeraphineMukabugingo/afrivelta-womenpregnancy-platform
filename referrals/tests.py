from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from organizations.models import Organization, OrganizationMembership

from .models import (
    ReferralRecord,
    ReferralStatusHistory,
    ServiceProvider,
)


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class ReferralWorkflowTests(TestCase):

    def setUp(self):
        # Create the authorized referral-management user.
        self.user = User.objects.create_user(
            username="referral_staff",
            password="TestPassword123!",
        )

        permission = Permission.objects.get(
            content_type__app_label="referrals",
            codename="manage_referrals",
        )
        self.user.user_permissions.add(permission)

        self.verifier = User.objects.create_user(
            username="provider_verifier",
            password="TestPassword123!",
        )

        # Create an active organization.
        self.organization = Organization.objects.create(
            name="Referral Test Organization",
            status=Organization.Status.ACTIVE,
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.STAFF,
            status=OrganizationMembership.Status.ACTIVE,
        )

        # Register a verified provider.
        self.provider = self.create_provider(
            self.organization,
            "Test Maternal Health Centre",
        )

        self.client.force_login(self.user)

    def create_provider(self, organization, name):
        return ServiceProvider.objects.create(
            organization=organization,
            name=name,
            category=ServiceProvider.Category.MATERNAL,
            description="Maternal health services.",
            address="Test Street",
            district="Gasabo",
            verification_status=(
                ServiceProvider.VerificationStatus.VERIFIED
            ),
            last_verified=date.today(),
            verified_by=self.verifier,
            created_by=self.verifier,
            is_active=True,
        )

    def create_referral(self, status=ReferralRecord.Status.NEW):
        record = ReferralRecord.objects.create(
            organization=self.organization,
            provider=self.provider,
            status=status,
            consent_confirmed=True,
            referring_staff=self.user,
            referral_date=date.today(),
            closed_at=(
                timezone.now()
                if status in (
                    ReferralRecord.Status.COMPLETED,
                    ReferralRecord.Status.CANCELLED,
                )
                else None
            ),
        )

        # Simulate the initial history created by the real creation view.
        ReferralStatusHistory.objects.create(
            referral=record,
            from_status="",
            to_status=status,
            changed_by=self.user,
            note="Referral created",
        )

        return record

    def referral_payload(self, record, status, notes=""):
        return {
            "organization": str(record.organization_id),
            "provider": str(record.provider_id),
            "assigned_staff": "",
            "consent_confirmed": "on",
            "referral_date": record.referral_date.isoformat(),
            "follow_up_due": "",
            "status": status,
            "non_identifying_notes": notes,
        }

    def test_referral_creation_records_initial_history(self):
        response = self.client.post(
            reverse("referral-create"),
            {
                "organization": str(self.organization.pk),
                "provider": str(self.provider.pk),
                "assigned_staff": "",
                "consent_confirmed": "on",
                "referral_date": date.today().isoformat(),
                "follow_up_due": "",
                "status": ReferralRecord.Status.NEW,
                "non_identifying_notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        record = ReferralRecord.objects.get(
            organization=self.organization
        )

        self.assertEqual(record.status, ReferralRecord.Status.NEW)
        self.assertEqual(record.referring_staff, self.user)

        history = record.status_history.get()

        self.assertEqual(history.from_status, "")
        self.assertEqual(history.to_status, ReferralRecord.Status.NEW)
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(history.note, "Referral created")
        self.assertIsNotNone(history.changed_at)

    def test_valid_status_change_is_recorded(self):
        record = self.create_referral()

        response = self.client.post(
            reverse("referral-update", kwargs={"pk": record.pk}),
            self.referral_payload(
                record,
                ReferralRecord.Status.SHARED,
            ),
        )

        self.assertEqual(response.status_code, 302)

        record.refresh_from_db()

        self.assertEqual(record.status, ReferralRecord.Status.SHARED)
        self.assertEqual(record.status_history.count(), 2)

        history = record.status_history.latest("changed_at")

        self.assertEqual(history.from_status, ReferralRecord.Status.NEW)
        self.assertEqual(history.to_status, ReferralRecord.Status.SHARED)
        self.assertEqual(history.changed_by, self.user)

    def test_invalid_status_transition_is_rejected(self):
        record = self.create_referral()

        response = self.client.post(
            reverse("referral-update", kwargs={"pk": record.pk}),
            self.referral_payload(
                record,
                ReferralRecord.Status.COMPLETED,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This status change is not permitted")

        record.refresh_from_db()

        self.assertEqual(record.status, ReferralRecord.Status.NEW)
        self.assertEqual(record.status_history.count(), 1)

    def test_editing_details_without_status_change_creates_no_history(self):
        record = self.create_referral()

        response = self.client.post(
            reverse("referral-update", kwargs={"pk": record.pk}),
            self.referral_payload(
                record,
                ReferralRecord.Status.NEW,
                notes="Routine service coordination.",
            ),
        )

        self.assertEqual(response.status_code, 302)

        record.refresh_from_db()

        self.assertEqual(record.status, ReferralRecord.Status.NEW)
        self.assertEqual(
            record.non_identifying_notes,
            "Routine service coordination.",
        )
        self.assertEqual(record.status_history.count(), 1)

    def test_closed_referral_cannot_be_reopened(self):
        record = self.create_referral(
            ReferralRecord.Status.COMPLETED
        )

        original_closed_at = record.closed_at

        response = self.client.post(
            reverse("referral-update", kwargs={"pk": record.pk}),
            self.referral_payload(
                record,
                ReferralRecord.Status.SHARED,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This referral is closed")

        record.refresh_from_db()

        self.assertEqual(
            record.status,
            ReferralRecord.Status.COMPLETED,
        )
        self.assertEqual(record.closed_at, original_closed_at)
        self.assertEqual(record.status_history.count(), 1)

    def test_referral_detail_displays_status_history(self):
        record = self.create_referral()

        response = self.client.get(
            reverse("referral-detail", kwargs={"pk": record.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, record.reference_code)
        self.assertContains(response, "Referral Status History")
        self.assertContains(response, "Referral created")

    def test_user_cannot_access_another_organizations_referral(self):
        other_organization = Organization.objects.create(
            name="Other Organization",
            status=Organization.Status.ACTIVE,
        )

        other_provider = self.create_provider(
            other_organization,
            "Other Maternal Health Centre",
        )

        other_user = User.objects.create_user(
            username="other_referral_staff",
            password="TestPassword123!",
        )

        other_record = ReferralRecord.objects.create(
            organization=other_organization,
            provider=other_provider,
            status=ReferralRecord.Status.NEW,
            consent_confirmed=True,
            referring_staff=other_user,
            referral_date=date.today(),
        )

        response = self.client.get(
            reverse(
                "referral-detail",
                kwargs={"pk": other_record.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_user_without_referral_permission_is_forbidden(self):
        unauthorized_user = User.objects.create_user(
            username="unauthorized_staff",
            password="TestPassword123!",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=unauthorized_user,
            role=OrganizationMembership.Role.STAFF,
            status=OrganizationMembership.Status.ACTIVE,
        )

        self.client.force_login(unauthorized_user)

        response = self.client.get(reverse("referral-list"))

        self.assertEqual(response.status_code, 403)


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"]
)
class ReferralFollowUpViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="followup_staff",
            password="TestPassword123!",
        )

        permission = Permission.objects.get(
            content_type__app_label="referrals",
            codename="manage_referrals",
        )
        self.user.user_permissions.add(permission)

        self.verifier = User.objects.create_user(
            username="followup_verifier",
            password="TestPassword123!",
        )

        self.organization = Organization.objects.create(
            name="Follow-up Test Organization",
            status=Organization.Status.ACTIVE,
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.STAFF,
            status=OrganizationMembership.Status.ACTIVE,
        )

        self.provider = self.create_provider(self.organization)

        self.client.force_login(self.user)

    def create_provider(self, organization):
        return ServiceProvider.objects.create(
            organization=organization,
            name="Follow-up Health Centre",
            category=ServiceProvider.Category.MATERNAL,
            description="Health and support services.",
            address="Test Street",
            district="Gasabo",
            verification_status=ServiceProvider.VerificationStatus.VERIFIED,
            last_verified=date.today(),
            verified_by=self.verifier,
            created_by=self.verifier,
            is_active=True,
        )

    def create_referral(
        self,
        *,
        status=ReferralRecord.Status.NEW,
        follow_up_due=None,
        assigned_staff=None,
        organization=None,
        provider=None,
    ):
        organization = organization or self.organization
        provider = provider or self.provider

        return ReferralRecord.objects.create(
            organization=organization,
            provider=provider,
            status=status,
            consent_confirmed=True,
            referring_staff=self.user,
            assigned_staff=assigned_staff,
            referral_date=timezone.localdate(),
            follow_up_due=follow_up_due,
            closed_at=(
                timezone.now()
                if status in (
                    ReferralRecord.Status.COMPLETED,
                    ReferralRecord.Status.CANCELLED,
                )
                else None
            ),
        )

    def get_sections(self, response):
        return {
            section["title"]: set(
                section["records"].values_list("pk", flat=True)
            )
            for section in response.context["sections"]
        }

    def test_follow_ups_are_classified_into_correct_sections(self):
        today = timezone.localdate()

        overdue = self.create_referral(
            follow_up_due=today - timezone.timedelta(days=2),
            assigned_staff=self.user,
        )

        due_today = self.create_referral(
            follow_up_due=today,
            assigned_staff=self.user,
        )

        upcoming = self.create_referral(
            status=ReferralRecord.Status.CONNECTED,
            follow_up_due=today + timezone.timedelta(days=3),
            assigned_staff=self.user,
        )

        unscheduled_unassigned = self.create_referral()

        completed_overdue = self.create_referral(
            status=ReferralRecord.Status.COMPLETED,
            follow_up_due=today - timezone.timedelta(days=1),
            assigned_staff=self.user,
        )

        response = self.client.get(
            reverse("referral-follow-up-list")
        )

        self.assertEqual(response.status_code, 200)

        sections = self.get_sections(response)

        self.assertIn(
            overdue.pk,
            sections["Overdue Follow-ups"],
        )
        self.assertIn(
            due_today.pk,
            sections["Due Today"],
        )
        self.assertIn(
            upcoming.pk,
            sections["Upcoming Follow-ups"],
        )
        self.assertIn(
            unscheduled_unassigned.pk,
            sections["Unassigned Referrals"],
        )
        self.assertIn(
            unscheduled_unassigned.pk,
            sections["Unscheduled Follow-ups"],
        )

        self.assertNotIn(
            completed_overdue.pk,
            sections["Overdue Follow-ups"],
        )

    def test_follow_up_page_excludes_other_organizations(self):
        other_organization = Organization.objects.create(
            name="Another Follow-up Organization",
            status=Organization.Status.ACTIVE,
        )

        other_provider = self.create_provider(other_organization)

        other_user = User.objects.create_user(
            username="other_followup_user",
            password="TestPassword123!",
        )

        other_referral = self.create_referral(
            organization=other_organization,
            provider=other_provider,
            follow_up_due=(
                timezone.localdate() - timezone.timedelta(days=2)
            ),
        )

        response = self.client.get(
            reverse("referral-follow-up-list")
        )

        self.assertEqual(response.status_code, 200)

        sections = self.get_sections(response)

        for record_ids in sections.values():
            self.assertNotIn(other_referral.pk, record_ids)

    def test_follow_up_page_requires_referral_permission(self):
        unauthorized_user = User.objects.create_user(
            username="followup_unauthorized",
            password="TestPassword123!",
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=unauthorized_user,
            role=OrganizationMembership.Role.STAFF,
            status=OrganizationMembership.Status.ACTIVE,
        )

        self.client.force_login(unauthorized_user)

        response = self.client.get(
            reverse("referral-follow-up-list")
        )

        self.assertEqual(response.status_code, 403)

    def test_follow_up_page_requires_login(self):
        self.client.logout()

        response = self.client.get(
            reverse("referral-follow-up-list")
        )

        self.assertEqual(response.status_code, 302)
