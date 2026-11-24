"""Private working-window screens; calculations and writes stay in services."""

from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from .calendar import calendar_date
from .intervals import date_bounds
from .models import WorkingDateOverride
from .working_forms import (
    OverrideRows, RestoreWorkingDateForm, WindowRows, WorkingDateForm, WorkingScheduleForm, attach_errors,
)
from .working_windows import (
    WORKING_ZONE, remove_working_date_override, set_working_date_override,
    set_working_schedule, working_schedule_editor_initial, working_window_screen,
)


def _screen_url(day):
    return reverse("scheduling:working_windows") + "?" + urlencode({"date": day.isoformat()})


class WorkingDateMixin:
    def selected_date(self):
        if "date" in self.request.GET:
            return calendar_date(self.request.GET["date"])
        return timezone.localdate(timezone.now(), ZoneInfo(WORKING_ZONE))


class WorkingWindowsView(LoginRequiredMixin, WorkingDateMixin, TemplateView):
    template_name = "scheduling/working_windows.html"

    def get(self, request, *args, **kwargs):
        try:
            context = working_window_screen(owner=request.user, anchor=self.selected_date())
        except ValidationError as error:
            return HttpResponseBadRequest(" ".join(error.messages))
        return self.render_to_response(self.get_context_data(screen=context))


class WorkingRowsView(LoginRequiredMixin, WorkingDateMixin, TemplateView):
    template_name = "scheduling/working_editor.html"
    prefix = "windows"
    kind = "weekly"
    header_class = WorkingScheduleForm
    rowset_class = WindowRows
    title = "Set weekly working windows"
    description = "Choose when you are willing to work each week, before commitments are subtracted. Multiple windows per weekday and overnight hours are supported."

    def header_initial(self):
        return self.editor_initial()["header"]

    def editor_initial(self):
        if not hasattr(self, "_editor_initial"):
            self._editor_initial = working_schedule_editor_initial(owner=self.request.user, effective_from=self.selected_date())
        return self._editor_initial

    def rows_initial(self):
        return self.editor_initial()["windows"]

    def header(self, data=None):
        return self.header_class(data, initial=self.header_initial())

    def render_editor(self, form, rows, **kwargs):
        return self.render_to_response(self.get_context_data(
            form=form, rows=rows, kind=self.kind, editor_title=self.title, description=self.description,
            return_url=_screen_url(self.header_initial().get("local_date", self.selected_date())), **kwargs,
        ))

    def get(self, request, *args, **kwargs):
        try:
            return self.render_editor(self.header(), self.rowset_class(initial=self.rows_initial(), prefix=self.prefix))
        except ValidationError as error:
            return HttpResponseBadRequest(" ".join(error.messages))

    def post(self, request, *args, **kwargs):
        try:
            form = self.header(request.POST)
            data = request.POST.copy()
            adding = data.get("action") == "add_window"
            if adding:
                try:
                    count = int(data.get(f"{self.prefix}-TOTAL_FORMS", ""))
                except ValueError:
                    count = -1
                if 0 <= count < 100:
                    data[f"{self.prefix}-TOTAL_FORMS"] = str(count + 1)
            # Posted rows describe the complete replacement pattern. Do not
            # seed extra bound forms from current database rows: identical data
            # could otherwise look unchanged and be skipped as an empty extra.
            rows = self.rowset_class(data, prefix=self.prefix)
        except ValidationError as error:
            return HttpResponseBadRequest(" ".join(error.messages))
        if adding:
            return self.render_editor(form, rows)
        form_valid, rows_valid = form.is_valid(), rows.is_valid()
        if not (form_valid and rows_valid):
            return self.render_editor(form, rows)
        return self.save_rows(form, rows)

    def save_rows(self, form, rows):
        windows = rows.specs()
        if not windows and not form.cleaned_data["no_windows"]:
            form.add_error("no_windows", "Add a working window, or explicitly choose no weekly working windows.")
        elif windows and form.cleaned_data["no_windows"]:
            form.add_error("no_windows", "Remove all listed windows before choosing no weekly working windows.")
        else:
            try:
                set_working_schedule(owner=self.request.user, effective_from=form.cleaned_data["effective_from"], windows=windows)
            except ValidationError as error:
                attach_errors(form, error)
            else:
                messages.success(self.request, "Weekly working windows saved. Earlier schedules are preserved.")
                return HttpResponseRedirect(_screen_url(form.cleaned_data["effective_from"]))
        return self.render_editor(form, rows)


class WorkingOverrideView(WorkingRowsView):
    prefix = "intervals"
    kind = "date"
    header_class = WorkingDateForm
    rowset_class = OverrideRows
    title = "Set working hours for one date"
    description = "Replace the entire date's working windows, including overnight hours carried in from the previous date. Commitments are still subtracted when calculating work availability."

    def get_override(self):
        if not hasattr(self, "override"):
            self.override = get_object_or_404(WorkingDateOverride.objects.prefetch_related("intervals"),
                                              pk=self.kwargs["pk"], owner=self.request.user) if "pk" in self.kwargs else None
        return self.override

    def header_initial(self):
        override = self.get_override()
        return {"local_date": override.local_date if override else self.selected_date(),
                "closed_all_day": not override.intervals.all() if override else False}

    def header(self, data=None):
        form = super().header(data)
        if self.get_override():
            form.fields["local_date"].disabled = True
        return form

    def rows_initial(self):
        override = self.get_override()
        if override is None:
            return []
        zone = ZoneInfo(override.time_zone)
        _, upper = date_bounds(override.local_date, override.time_zone)
        result = []
        for item in override.intervals.all():
            start, end = item.starts_at.astimezone(zone), item.ends_at.astimezone(zone)
            result.append({"start_time": start.time(), "end_time": end.time(),
                           "end_at_midnight": item.ends_at == upper,
                           "second_start": bool(start.fold), "second_end": bool(end.fold)})
        return result

    def save_rows(self, form, rows):
        resolved = rows.resolved_rows(form.cleaned_data["local_date"])
        notes = tuple(note for item in resolved for note in item.notes)
        if any(row.errors for row in rows.forms if not row.cleaned_data.get("DELETE")):
            return self.render_editor(form, rows, clock_notes=notes)
        if resolved and form.cleaned_data["closed_all_day"]:
            form.add_error("closed_all_day", "Remove all intervals before choosing unavailable all day.")
        elif not resolved and not form.cleaned_data["closed_all_day"]:
            form.add_error("closed_all_day", "Add working hours, or explicitly choose unavailable all day.")
        else:
            try:
                override = set_working_date_override(owner=self.request.user, local_date=form.cleaned_data["local_date"],
                                                       intervals=[item.interval for item in resolved])
            except ValidationError as error:
                attach_errors(form, error)
            else:
                messages.success(self.request, "Working hours for this date saved.")
                for note in notes:
                    messages.info(self.request, note)
                return HttpResponseRedirect(_screen_url(override.local_date))
        return self.render_editor(form, rows, clock_notes=notes)


class WorkingOverrideRemoveView(LoginRequiredMixin, FormView):
    form_class = RestoreWorkingDateForm
    template_name = "scheduling/working_override_remove.html"

    def get_override(self):
        if not hasattr(self, "override"):
            self.override = get_object_or_404(WorkingDateOverride.objects.prefetch_related("intervals"),
                                              pk=self.kwargs["pk"], owner=self.request.user)
        return self.override

    def get_form_kwargs(self):
        self.get_override()
        return super().get_form_kwargs()

    def get_context_data(self, **kwargs):
        override = self.get_override()
        return {**super().get_context_data(**kwargs), "override": override, "return_url": _screen_url(override.local_date)}

    def form_valid(self, form):
        override = self.get_override()
        remove_working_date_override(owner=self.request.user, override_id=override.pk)
        messages.success(self.request, "Date override removed. Weekly working windows apply again.")
        return HttpResponseRedirect(_screen_url(override.local_date))
