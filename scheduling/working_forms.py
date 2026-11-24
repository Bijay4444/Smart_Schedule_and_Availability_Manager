"""Working-window editor inputs; scheduling rules and clock resolution stay in services."""

from calendar import day_name

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from .working_windows import WindowSpec, resolve_override_interval


def attach_errors(form, error):
    if hasattr(error, "message_dict"):
        for name, messages in error.message_dict.items():
            form.add_error(name if name in form.fields else None, messages)
    else:
        form.add_error(None, error)


class WorkingScheduleForm(forms.Form):
    effective_from = forms.DateField(label="Use this weekly schedule from", widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
                                     help_text="Earlier schedules are preserved. This replaces the weekly pattern and any later planned patterns from the selected date.")
    no_windows = forms.BooleanField(required=False, label="No weekly working windows from this date",
                                    widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class WorkingDateForm(forms.Form):
    local_date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    closed_all_day = forms.BooleanField(required=False, label="Unavailable for work all day",
                                       widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class WindowRowForm(forms.Form):
    weekday = forms.TypedChoiceField(choices=[("", "Choose a day"), *enumerate(day_name)], coerce=int,
                                     widget=forms.Select(attrs={"class": "form-select"}))
    start_time = forms.TimeField(label="Start time", widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}))
    end_time = forms.TimeField(label="End time", widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}))
    ends_next_day = forms.BooleanField(required=False, label="Ends the following day", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def clean(self):
        data = super().clean()
        if data.get("start_time") and data.get("end_time") and not data.get("ends_next_day"):
            if data["end_time"] <= data["start_time"]:
                self.add_error("end_time", "End must follow start, or select the following day.")
        return data

    def window_spec(self):
        data = self.cleaned_data
        return WindowSpec(data["weekday"], data["start_time"], data["end_time"], int(data["ends_next_day"]))


class WindowFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        rows = self.specs()
        if len(set(rows)) != len(rows):
            raise ValidationError("Remove exact duplicate windows. Overlapping windows with different hours are allowed.")

    def specs(self):
        return [form.window_spec() for form in self.forms if form.cleaned_data and not form.cleaned_data.get("DELETE")]


class OverrideRowForm(forms.Form):
    start_time = forms.TimeField(label="Start time", widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}))
    end_time = forms.TimeField(required=False, label="End time", widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}))
    end_at_midnight = forms.BooleanField(required=False, label="End at the following midnight (24:00)",
                                         help_text="Leave the end time blank or enter 00:00. For overnight hours, add an override on each date.",
                                         widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    second_start = forms.BooleanField(required=False, label="Use the second repeated hour for the start", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    second_end = forms.BooleanField(required=False, label="Use the second repeated hour for the end", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def resolve(self, local_date):
        return resolve_override_interval(local_date=local_date, **{
            name: self.cleaned_data[name] for name in ("start_time", "end_time", "end_at_midnight", "second_start", "second_end")
        })


class OverrideFormSet(BaseFormSet):
    def resolved_rows(self, local_date):
        resolved = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            try:
                resolved.append(form.resolve(local_date))
            except ValidationError as error:
                attach_errors(form, error)
        return resolved


WindowRows = formset_factory(WindowRowForm, formset=WindowFormSet, extra=1, can_delete=True,
                              max_num=100, absolute_max=100, validate_max=True)
OverrideRows = formset_factory(OverrideRowForm, formset=OverrideFormSet, extra=1, can_delete=True,
                                max_num=100, absolute_max=100, validate_max=True)


class RestoreWorkingDateForm(forms.Form):
    confirm = forms.BooleanField(label="Remove this date override and use the weekly working windows again.",
                                 widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
