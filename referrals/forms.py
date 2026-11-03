from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from organizations.models import Organization, OrganizationMembership
from .models import ReferralRecord, ServiceProvider

User = get_user_model()


class ServiceProviderForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        required=True,
        label="Owning organization",
    )
    class Meta:
        model = ServiceProvider
        fields = (
            "organization",
            "name",
            "category",
            "description",
            "phone",
            "email",
            "website_url",
            "address",
            "district",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, organizations=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = (
            organizations if organizations is not None
            else Organization.objects.none()
        )


class ReferralRecordForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        required=True,
        label="Referring organization",
    )
    class Meta:
        model = ReferralRecord
        fields = (
            "organization",
            "provider",
            "assigned_staff",
            "consent_confirmed",
            "referral_date",
            "follow_up_due",
            "status",
            "non_identifying_notes",
        )
        widgets = {
            "referral_date": forms.DateInput(attrs={"type": "date"}),
            "follow_up_due": forms.DateInput(attrs={"type": "date"}),
            "non_identifying_notes": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": (
                    "Operational notes only. Do not enter names, "
                    "diagnoses or contact details."
                ),
            }),
        }

    def __init__(self, *args, organizations=None, **kwargs):
        super().__init__(*args, **kwargs)

        organizations = (
            organizations if organizations is not None
            else Organization.objects.none()
        )

        self.fields["organization"].queryset = organizations

        organization_id = (
            self.data.get("organization")
            if self.is_bound
            else self.initial.get("organization")
        )

        if not organization_id and self.instance.pk:
            organization_id = self.instance.organization_id

        self.fields["provider"].queryset = (
            ServiceProvider.objects.none()
        )
        self.fields["assigned_staff"].queryset = User.objects.none()

        if organization_id:
            self.fields["provider"].queryset = (
                ServiceProvider.objects.filter(
                    is_active=True,
                    verification_status=ServiceProvider.VerificationStatus.VERIFIED,
                ).filter(
                    Q(organization_id=organization_id) | Q(is_shared=True)
                )
            )

            self.fields["assigned_staff"].queryset = User.objects.filter(
                organization_memberships__organization_id=organization_id,
                organization_memberships__status=OrganizationMembership.Status.ACTIVE,
                is_active=True,
            ).distinct()

        self.fields["consent_confirmed"].label = (
            "Appropriate consent has been confirmed"
        )

    def clean_consent_confirmed(self):
        confirmed = self.cleaned_data.get("consent_confirmed")
        if not confirmed:
            raise forms.ValidationError(
                "Confirm appropriate consent before saving this referral."
            )
        return confirmed

    def clean_non_identifying_notes(self):
        value = self.cleaned_data.get("non_identifying_notes", "")
        forbidden = (
            "diagnosis:", "patient name:", "phone number:",
            "date of birth:", "national id:",
        )
        if any(term in value.lower() for term in forbidden):
            raise forms.ValidationError(
                "Remove identifying or detailed clinical information."
            )
        return value
