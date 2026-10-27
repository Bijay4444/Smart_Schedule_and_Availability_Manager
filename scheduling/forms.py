from django import forms
from django.db.models import Q

from .models import Commitment, CommitmentSource


class SourceForm(forms.ModelForm):
    class Meta:
        model = CommitmentSource
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "color": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.owner = owner
        self.owner = owner

    def clean_name(self):
        name = self.cleaned_data["name"]
        duplicates = CommitmentSource.objects.filter(owner=self.owner, name=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("You already have a source with this name.")
        return name


class CommitmentForm(forms.ModelForm):
    confirm_conflicts = forms.BooleanField(
        required=False,
        label="I understand these conflicts and want to save this commitment.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Commitment
        fields = ["title", "source", "starts_at", "ends_at"]
        labels = {"starts_at": "Starts", "ends_at": "Ends"}
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "source": forms.Select(attrs={"class": "form-select"}),
            "starts_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "form-control"},
            ),
            "ends_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "form-control"},
            ),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_sources = Q(archived_at__isnull=True)
        if self.instance.pk:
            allowed_sources |= Q(pk=self.instance.source_id)
        self.fields["source"].queryset = CommitmentSource.objects.filter(
            allowed_sources, owner=owner
        )
        self.fields["source"].empty_label = "Choose a source"
        self.fields["ends_at"].help_text = (
            "For an overnight shift, choose the following date for the end."
        )
