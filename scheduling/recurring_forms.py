"""Parse recurring editor inputs; schedule changes are performed by services."""

from datetime import UTC, datetime

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import CommitmentSource
from .time_resolution import resolve_local_time


class ReviewForm(forms.Form):
    confirm_review = forms.BooleanField(required=False, label="I have reviewed these dates, times, and warnings.")
    review_token = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                continue
            field.widget.attrs["class"] = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"


class PatternForm(ReviewForm):
    title = forms.CharField(max_length=160)
    weekdays = forms.TypedMultipleChoiceField(
        choices=list(enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))),
        coerce=int, widget=forms.CheckboxSelectMultiple, label="Repeats on",
    )
    start_time = forms.TimeField(widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}))
    end_time = forms.TimeField(widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}))
    ends_next_day = forms.BooleanField(required=False, label="Ends the following day")

    def clean(self):
        data = super().clean()
        if data.get("start_time") and data.get("end_time") and not data.get("ends_next_day"):
            if data["end_time"] <= data["start_time"]:
                self.add_error("end_time", "End must follow start, or select the following day.")
        return data

    def values(self):
        data = self.cleaned_data
        return {"title": data["title"], "weekdays": data["weekdays"], "start_time": data["start_time"],
                "end_time": data["end_time"], "end_day_offset": int(data["ends_next_day"])}


class SeriesCreateForm(PatternForm):
    source = forms.ModelChoiceField(queryset=CommitmentSource.objects.none(), empty_label="Choose a source")
    starts_on = forms.DateField(label="First date", widget=forms.DateInput(attrs={"type": "date"}))
    ends_on = forms.DateField(required=False, label="Last start date (optional)",
                              widget=forms.DateInput(attrs={"type": "date"}),
                              help_text="Leave blank to repeat indefinitely. A final overnight occurrence may finish the following day.")

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = CommitmentSource.objects.filter(owner=owner, archived_at__isnull=True)
        self.fields["source"].widget.attrs["class"] = "form-select"
        self.order_fields(["title", "source", "starts_on", "ends_on", "weekdays", "start_time", "end_time", "ends_next_day"])

    def clean(self):
        data = super().clean()
        if data.get("starts_on") and data.get("ends_on") and data["ends_on"] < data["starts_on"]:
            self.add_error("ends_on", "The last date must be on or after the first date.")
        return data

    def values(self):
        return {**super().values(), "source_id": self.cleaned_data["source"].pk,
                "starts_on": self.cleaned_data["starts_on"], "ends_on": self.cleaned_data["ends_on"]}


class SeriesReviseForm(PatternForm):
    effective_from = forms.DateField(label="Change from", widget=forms.DateInput(attrs={"type": "date"}),
                                     help_text="All selected weekdays change from this date. Earlier dates and explicit one-off changes are preserved.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(["effective_from", "title", "weekdays", "start_time", "end_time", "ends_next_day"])

    def values(self):
        return {**super().values(), "effective_from": self.cleaned_data["effective_from"]}


class EndSeriesForm(forms.Form):
    ends_before = forms.DateField(label="Stop occurrences starting on or after", widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                                 help_text="Earlier occurrences remain. Replacements are stopped by their original date, even if moved elsewhere.")
    confirm = forms.BooleanField(label="End this recurring commitment from the selected date.", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class CancelOccurrenceForm(forms.Form):
    confirm = forms.BooleanField(label="Cancel this occurrence only.", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class OccurrenceChangeForm(ReviewForm):
    replacement_source = forms.ModelChoiceField(queryset=CommitmentSource.objects.none(), empty_label="Choose a source", label="Source")
    replacement_title = forms.CharField(max_length=160, label="Title")
    starts_at = forms.CharField(label="Starts", widget=forms.TextInput(attrs={"type": "datetime-local"}))
    ends_at = forms.CharField(label="Ends", widget=forms.TextInput(attrs={"type": "datetime-local"}))
    second_start = forms.BooleanField(required=False, label="Use the second repeated hour for the start",
                                      help_text="Only applies when the fall-back clock repeats this time.")
    second_end = forms.BooleanField(required=False, label="Use the second repeated hour for the end")

    def __init__(self, *args, owner, series, original_date, **kwargs):
        super().__init__(*args, **kwargs)
        self.series = series
        self.original_date = original_date
        existing = series.exceptions.filter(original_start_date=original_date).first()
        allowed = Q(archived_at__isnull=True) | Q(pk=series.source_id)
        if existing and existing.replacement_source_id:
            allowed |= Q(pk=existing.replacement_source_id)
        self.fields["replacement_source"].queryset = CommitmentSource.objects.filter(allowed, owner=owner)
        self.fields["replacement_source"].widget.attrs["class"] = "form-select"
        self.order_fields(["replacement_title", "replacement_source", "starts_at", "ends_at", "second_start", "second_end"])
        self.clock_notes = []

    def clean(self):
        data = super().clean()
        for field, second in (("starts_at", "second_start"), ("ends_at", "second_end")):
            if field not in data:
                continue
            try:
                local = datetime.fromisoformat(data[field])
                result = resolve_local_time(local, self.series.time_zone)
                if data.get(second):
                    if result.adjustment != "fold_first":
                        raise ValidationError("This time is not repeated. Clear the second-hour option.")
                    value = result.value.replace(fold=1)
                    self.clock_notes.append(f"{self.fields[field].label}: second repeated time, {value:%d %b %Y %H:%M %Z}.")
                else:
                    value = result.value
                    if result.adjustment:
                        explanation = "moved forward for the clock change" if result.adjustment == "gap_shift_forward" else "first repeated time"
                        self.clock_notes.append(f"{self.fields[field].label}: {explanation}, {value:%d %b %Y %H:%M %Z}.")
                data[field] = value
            except (TypeError, ValueError):
                self.add_error(field, "Enter a local date and time.")
            except ValidationError as error:
                self.add_error(field, error)
        if isinstance(data.get("starts_at"), datetime) and isinstance(data.get("ends_at"), datetime):
            if data["ends_at"].astimezone(UTC) <= data["starts_at"].astimezone(UTC):
                self.add_error("ends_at", "End must be after start, including after the clock change.")
        return data

    def values(self):
        data = self.cleaned_data
        return {"series_id": self.series.pk, "original_start_date": self.original_date,
                "replacement_source_id": data["replacement_source"].pk,
                "replacement_title": data["replacement_title"], "starts_at": data["starts_at"], "ends_at": data["ends_at"]}
