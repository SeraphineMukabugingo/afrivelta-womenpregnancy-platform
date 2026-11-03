from django import forms

from organizations.models import Organization
from .models import ContentItem, ContentSource


class ContentItemForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        required=True,
        label="Owning organization",
    )
    class Meta:
        model = ContentItem
        fields = [
            "organization",
            "title",
            "content_type",
            "topic",
            "language",
            "intended_audience",
            "summary",
            "body",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 10}),
        }

    def __init__(self, *args, organizations=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = (
            organizations if organizations is not None
            else Organization.objects.none()
        )
        self.fields["organization"].empty_label = "Select organization"

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ContentSourceForm(forms.ModelForm):
    class Meta:
        model = ContentSource
        fields = [
            "source_organization",
            "title",
            "url",
            "last_verified",
            "notes",
        ]
        widgets = {
            "last_verified": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
