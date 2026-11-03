from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group

from .models import Organization, OrganizationMembership

User = get_user_model()

STAFF_GROUPS = [
    "Platform Administrator",
    "Programme Manager",
    "Education Officer",
    "Education Reviewer",
    "Referral Coordinator",
    "Referral Verifier",
    "Healthcare Partner",
    "Monitoring and Evaluation Officer",
    "Data Analyst",
    "General Staff",
]


class StaffCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        empty_label="Select an organization",
    )

    organization_role = forms.ChoiceField(
        choices=OrganizationMembership.Role.choices,
    )

    roles = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Department roles",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(
        self,
        *args,
        organizations=None,
        allow_platform_admin=False,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.fields["organization"].queryset = (
            organizations if organizations is not None
            else Organization.objects.none()
        )

        allowed_groups = STAFF_GROUPS.copy()

        if not allow_platform_admin:
            allowed_groups.remove("Platform Administrator")

        self.fields["roles"].queryset = Group.objects.filter(
            name__in=allowed_groups
        ).order_by("name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True

        if commit:
            user.save()

        return user


class StaffUpdateForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        label="Organization",
    )

    organization_role = forms.ChoiceField(
        choices=OrganizationMembership.Role.choices,
    )

    membership_status = forms.ChoiceField(
        choices=OrganizationMembership.Status.choices,
        label="Organization membership status",
    )

    roles = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Department roles",
    )

    account_active = forms.BooleanField(
        required=False,
        label="Account active",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(
        self,
        *args,
        organizations=None,
        allow_platform_admin=False,
        allow_account_control=False,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        organizations = (
            organizations if organizations is not None
            else Organization.objects.none()
        )

        self.fields["organization"].queryset = organizations

        allowed_groups = STAFF_GROUPS.copy()

        if not allow_platform_admin:
            allowed_groups.remove("Platform Administrator")

        self.fields["roles"].queryset = Group.objects.filter(
            name__in=allowed_groups
        ).order_by("name")

        if self.instance and self.instance.pk:
            self.fields["roles"].initial = self.instance.groups.all()
            self.fields["account_active"].initial = self.instance.is_active

            membership = OrganizationMembership.objects.filter(
                user=self.instance,
                organization__in=organizations,
            ).select_related("organization").first()

            if membership:
                self.initial.setdefault(
                    "organization", membership.organization_id
                )
                self.initial.setdefault(
                    "organization_role", membership.role
                )
                self.initial.setdefault(
                    "membership_status", membership.status
                )

        if not allow_account_control:
            self.fields.pop("account_active", None)
