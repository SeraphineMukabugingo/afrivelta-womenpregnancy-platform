from django import forms
from django.contrib.auth import get_user_model

from organizations.models import Organization, OrganizationMembership
from .models import Programme, ProgrammeActivity, ProgrammeMilestone

User = get_user_model()


class ProgrammeForm(forms.ModelForm):
    class Meta:
        model = Programme
        fields = [
            "organization",
            "name",
            "description",
            "objectives",
            "target_group",
            "country",
            "district_or_city",
            "start_date",
            "end_date",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "objectives": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, organizations=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["organization"].queryset = (
            organizations
            if organizations is not None
            else Organization.objects.none()
        )

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ProgrammeActivityForm(forms.ModelForm):
    progress_percent = forms.IntegerField(
        min_value=0,
        max_value=100,
        initial=0,
        label="Completion percentage",
    )

    class Meta:
        model = ProgrammeActivity
        fields = [
            "title",
            "activity_type",
            "description",
            "start_date",
            "end_date",
            "assigned_to",
            "status",
            "progress_percent",
            "notes",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, programme=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].queryset = User.objects.none()

        if programme is not None:
            member_ids = OrganizationMembership.objects.filter(
                organization=programme.organization,
                status=OrganizationMembership.Status.ACTIVE,
            ).values_list("user_id", flat=True)

            self.fields["assigned_to"].queryset = (
                User.objects.filter(pk__in=member_ids).distinct()
            )

        self.fields["assigned_to"].empty_label = "Unassigned"

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error(
                "end_date",
                "The end date must be on or after the start date.",
            )

        return cleaned_data


class ProgrammeMilestoneForm(forms.ModelForm):
    class Meta:
        model = ProgrammeMilestone
        fields = [
            "title",
            "description",
            "due_date",
            "status",
            "responsible_user",
            "completion_date",
            "evidence_summary",
            "evidence_reference",
            "notes",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "completion_date": forms.DateInput(attrs={"type": "date"}),
            "evidence_summary": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, programme=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.programme = programme

        self.fields["responsible_user"].required = False
        self.fields["responsible_user"].queryset = User.objects.none()
        self.fields["responsible_user"].empty_label = "Unassigned"

        if programme is not None:
            member_ids = OrganizationMembership.objects.filter(
                organization=programme.organization,
                status=OrganizationMembership.Status.ACTIVE,
            ).values_list("user_id", flat=True)

            self.fields["responsible_user"].queryset = (
                User.objects.filter(pk__in=member_ids).distinct()
            )

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        due_date = cleaned_data.get("due_date")
        completion_date = cleaned_data.get("completion_date")
        status = cleaned_data.get("status")

        if self.programme is not None and due_date:
            if not (
                self.programme.start_date
                <= due_date
                <= self.programme.end_date
            ):
                self.add_error(
                    "due_date",
                    "The milestone due date must fall within "
                    "the programme dates.",
                )

        if completion_date and due_date and completion_date < due_date:
            if status == ProgrammeMilestone.Status.ACHIEVED:
                self.add_error(
                    "completion_date",
                    "Check the completion date against the milestone due date.",
                )

        return cleaned_data
