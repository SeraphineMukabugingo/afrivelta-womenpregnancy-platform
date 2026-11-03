from django import forms
from django.contrib.auth import get_user_model

from .models import Organization, OrganizationMembership

User = get_user_model()


class OrganizationAdminForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            "name",
            "legal_name",
            "organization_type",
            "country",
            "district_or_city",
            "website",
            "contact_email",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class MembershipCreateForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Staff account",
    )

    class Meta:
        model = OrganizationMembership
        fields = ("user", "role", "status")

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

        self.fields["user"].queryset = User.objects.filter(
            is_active=True,
            is_superuser=False,
        ).order_by("username")

    def clean_user(self):
        user = self.cleaned_data["user"]

        if OrganizationMembership.objects.filter(
            organization=self.organization,
            user=user,
        ).exists():
            raise forms.ValidationError(
                "This user already has a membership in this organization."
            )

        return user

    def clean(self):
        cleaned = super().clean()

        if (
            self.organization
            and self.organization.status != Organization.Status.ACTIVE
            and cleaned.get("status") == OrganizationMembership.Status.ACTIVE
        ):
            self.add_error(
                "status",
                "Activate the organization before activating its members.",
            )

        return cleaned


class MembershipUpdateForm(forms.ModelForm):
    class Meta:
        model = OrganizationMembership
        fields = ("role", "status")

    def clean_status(self):
        status = self.cleaned_data["status"]

        if (
            self.instance.organization.status != Organization.Status.ACTIVE
            and status == OrganizationMembership.Status.ACTIVE
        ):
            raise forms.ValidationError(
                "Activate the organization before activating its members."
            )

        return status
