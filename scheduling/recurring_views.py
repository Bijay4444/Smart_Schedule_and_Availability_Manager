"""Authenticated recurring editors; temporal rules and writes stay in services."""

from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView, ListView

from .calendar import calendar_date
from .models import RecurringSeries
from .recurrence import cancel_occurrence, end_series
from .recurring_forms import (
    CancelOccurrenceForm, EndSeriesForm, OccurrenceChangeForm, SeriesCreateForm, SeriesReviseForm,
)
from .recurring_workflow import (
    ReviewRequired, edit_initial, occurrence_initial, save_occurrence_change, save_recurring_series,
)


def _form_errors(form, error):
    if hasattr(error, "message_dict"):
        for name, errors in error.message_dict.items():
            form.add_error(name if name in form.fields else None, errors)
    else:
        form.add_error(None, error)


class SeriesListView(LoginRequiredMixin, ListView):
    template_name = "scheduling/series_list.html"
    context_object_name = "series_list"

    def get_queryset(self):
        return RecurringSeries.objects.filter(source__owner=self.request.user).select_related("source").prefetch_related(
            "revisions__weekdays", "exceptions",
        ).order_by("source__name", "pk")


class RecurringEditorView(LoginRequiredMixin, FormView):
    template_name = "scheduling/recurring_editor.html"
    title = "Recurring commitment"
    description = "Times use Halifax time. Review the schedule before saving."
    needs_review = True

    def selected_date(self, default=None):
        if "date" in self.request.GET:
            try:
                return calendar_date(self.request.GET["date"])
            except ValidationError:
                raise Http404("Invalid calendar date.")
        return default or timezone.localdate(timezone.now(), ZoneInfo("America/Halifax"))

    def get_series(self):
        if not hasattr(self, "series"):
            self.series = get_object_or_404(RecurringSeries.objects.select_related("source"),
                                          pk=self.kwargs["pk"], source__owner=self.request.user)
        return self.series

    def get_success_url(self):
        if "week" in self.request.GET:
            try:
                week = calendar_date(self.request.GET["week"])
                return reverse("scheduling:week") + "?" + urlencode({"week": week.isoformat()})
            except ValidationError:
                pass
        return reverse("scheduling:series_list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "editor_title": self.title,
                "description": self.description, "needs_review": self.needs_review,
                "return_url": self.get_success_url()}

    def form_valid(self, form):
        try:
            self.perform(form)
        except ReviewRequired as review:
            # Replace bound hidden data and clear acknowledgement for this new
            # preview, including when a previous signed review became stale.
            form.data = form.data.copy()
            form.data["review_token"] = review.token
            form.data["confirm_review"] = ""
            return self.render_to_response(self.get_context_data(form=form, preview=review.preview,
                                                                review_changed=review.changed))
        except ValidationError as error:
            _form_errors(form, error)
            return self.form_invalid(form)
        messages.success(self.request, "Recurring schedule saved.")
        return HttpResponseRedirect(self.get_success_url())

    def review_arguments(self, form):
        return {"owner": self.request.user, "values": form.values(),
                "review_token": form.cleaned_data["review_token"], "confirmed": form.cleaned_data["confirm_review"]}


class SeriesCreateView(RecurringEditorView):
    form_class = SeriesCreateForm
    title = "Add a recurring commitment"
    description = "Choose the weekdays and regular hours. Review checks the first 12 months, or through the last date if sooner."

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "owner": self.request.user}

    def get_initial(self):
        day = self.selected_date()
        return {"starts_on": day, "weekdays": [day.weekday()], "start_time": "09:00", "end_time": "10:00"}

    def perform(self, form):
        save_recurring_series(**self.review_arguments(form))


class SeriesReviseView(RecurringEditorView):
    form_class = SeriesReviseForm
    title = "Change future recurring hours"
    description = "Earlier dates stay as recorded. This change replaces all later regular rules and keeps explicit one-off changes. Review checks up to 12 months from the change date."

    def get_initial(self):
        series = self.get_series()
        first = max(self.selected_date(), series.starts_on)
        return edit_initial(owner=self.request.user, series_id=series.pk, effective_from=first)

    def perform(self, form):
        save_recurring_series(series_id=self.get_series().pk, **self.review_arguments(form))


class SeriesEndView(RecurringEditorView):
    form_class = EndSeriesForm
    title = "End a recurring commitment"
    description = "Stop future occurrences while keeping the earlier schedule. This also stops replacements whose original date is on or after the cutoff."
    needs_review = False

    def get_initial(self):
        self.get_series()
        return {"ends_before": self.selected_date()}

    def perform(self, form):
        end_series(owner=self.request.user, series_id=self.get_series().pk, ends_before=form.cleaned_data["ends_before"])


class OccurrenceEditorMixin:
    def original_date(self):
        try:
            return calendar_date(self.kwargs["original_date"])
        except ValidationError:
            raise Http404("Invalid occurrence date.")

    def occurrence_initial(self):
        try:
            return occurrence_initial(owner=self.request.user, series_id=self.get_series().pk,
                                      original_date=self.original_date())
        except ValidationError:
            raise Http404("No occurrence exists on that original date.")


class OccurrenceChangeView(OccurrenceEditorMixin, RecurringEditorView):
    form_class = OccurrenceChangeForm
    title = "Change one occurrence"
    description = "Choose the actual replacement dates and hours. The original occurrence is replaced; other weeks keep their regular schedule."

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "owner": self.request.user,
                "series": self.get_series(), "original_date": self.original_date()}

    def get_initial(self):
        return self.occurrence_initial()

    def perform(self, form):
        save_occurrence_change(**self.review_arguments(form))


class OccurrenceCancelView(OccurrenceEditorMixin, RecurringEditorView):
    form_class = CancelOccurrenceForm
    title = "Cancel one occurrence"
    description = "Cancel only this original occurrence, including any existing replacement. The recurring schedule continues on other dates."
    needs_review = False

    def get_initial(self):
        self.occurrence_initial()
        return {}

    def perform(self, form):
        cancel_occurrence(owner=self.request.user, series_id=self.get_series().pk,
                          original_start_date=self.original_date())
