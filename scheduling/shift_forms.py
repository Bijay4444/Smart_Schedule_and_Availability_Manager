"""Parse an unsaved shift in Halifax time, with explicit clock-change choices."""

from datetime import datetime
import re

from django import forms
from django.core.exceptions import ValidationError

from .intervals import query_interval
from .time_resolution import resolve_local_time
from .working_windows import WORKING_ZONE


class ProposedShiftForm(forms.Form):
    starts_at = forms.CharField(label="Shift starts", widget=forms.TextInput(
        attrs={"type": "datetime-local", "class": "form-control"}))
    ends_at = forms.CharField(label="Shift ends", help_text="For an overnight shift, choose the following date.",
                             widget=forms.TextInput(attrs={"type": "datetime-local", "class": "form-control"}))
    second_start = forms.BooleanField(required=False, label="Use the second repeated hour for the start",
                                      widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    second_end = forms.BooleanField(required=False, label="Use the second repeated hour for the end",
                                    widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def clean(self):
        data = super().clean()
        self.clock_notes = []
        for field, second in (("starts_at", "second_start"), ("ends_at", "second_end")):
            if field not in data:
                continue
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?", data[field]):
                    raise ValidationError("Enter a local date and time, without a UTC offset.")
                local = datetime.fromisoformat(data[field])
                if not 1 < local.year < 9999:
                    raise ValidationError("Choose a date between years 0002 and 9998.")
                resolution = resolve_local_time(local, WORKING_ZONE)
                value = resolution.value
                if data.get(second):
                    if resolution.adjustment != "fold_first":
                        raise ValidationError("This time is not repeated. Clear the second-hour option.")
                    value = value.replace(fold=1)
                    explanation = "second repeated time"
                elif resolution.adjustment == "gap_shift_forward":
                    explanation = "moved forward for the clock change"
                elif resolution.adjustment == "fold_first":
                    explanation = "first repeated time"
                else:
                    explanation = None
                if explanation:
                    self.clock_notes.append(f"{self.fields[field].label}: {explanation}, {value:%d %b %Y %H:%M:%S %Z}.")
                data[field] = value
            except (ValueError, OverflowError):
                self.add_error(field, "Enter a valid local date and time.")
            except ValidationError as error:
                self.add_error(field, error)
        if "starts_at" in data and "ends_at" in data:
            try:
                # Compare actual instants, including shifts spanning a repeated hour.
                query_interval(data["starts_at"], data["ends_at"])
            except ValidationError as error:
                self.add_error("ends_at", error)
        return data
