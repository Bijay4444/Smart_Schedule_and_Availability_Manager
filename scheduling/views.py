from datetime import datetime, time
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .calendar import calendar_date, calendar_for_user

from .forms import CommitmentForm, SourceForm
from .models import Commitment, CommitmentSource
from .services import ConflictingCommitments, commitments_for_user, save_commitment


class WeeklyCalendarView(LoginRequiredMixin, TemplateView):
    template_name = "scheduling/week.html"

    def get(self, request, *args, **kwargs):
        try:
            anchor = calendar_date(request.GET["week"]) if "week" in request.GET else None
            week = calendar_for_user(owner=request.user, anchor=anchor)
        except ValidationError as error:
            return HttpResponseBadRequest(" ".join(error.messages))
        return self.render_to_response(self.get_context_data(week=week))


class CommitmentListView(LoginRequiredMixin, ListView):
    template_name = "scheduling/commitment_list.html"
    context_object_name = "commitments"

    def get_queryset(self):
        return commitments_for_user(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sources"] = CommitmentSource.objects.filter(owner=self.request.user)
        return context


class SourceCreateView(LoginRequiredMixin, CreateView):
    form_class = SourceForm
    template_name = "scheduling/source_form.html"
    success_url = reverse_lazy("scheduling:commitment_list")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "owner": self.request.user}

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Source added. You can now add a commitment.")
        return response


class CommitmentFormMixin:
    form_class = CommitmentForm
    template_name = "scheduling/commitment_form.html"
    success_url = reverse_lazy("scheduling:commitment_list")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "owner": self.request.user}

    def get_initial(self):
        initial = super().get_initial()
        if not getattr(self, "object", None) and "date" in self.request.GET:
            try:
                day = calendar_date(self.request.GET["date"])
            except ValidationError:
                return initial
            initial.update(starts_at=datetime.combine(day, time(9)), ends_at=datetime.combine(day, time(10)))
        return initial

    def get_success_url(self):
        try:
            week = calendar_date(self.request.GET.get("week"))
        except ValidationError:
            return str(self.success_url)
        return reverse("scheduling:week") + "?" + urlencode({"week": week.isoformat()})

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "return_url": self.get_success_url()}

    def form_valid(self, form):
        commitment = form.save(commit=False)
        try:
            self.object = save_commitment(
                commitment=commitment,
                owner=self.request.user,
                confirm_conflicts=form.cleaned_data["confirm_conflicts"],
            )
        except ConflictingCommitments as error:
            return self.render_to_response(
                self.get_context_data(form=form, conflicts=error.conflicts)
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Commitment saved.")
        return HttpResponseRedirect(self.get_success_url())


class CommitmentCreateView(LoginRequiredMixin, CommitmentFormMixin, CreateView):
    model = Commitment


class OwnedCommitmentMixin:
    def get_queryset(self):
        return Commitment.objects.filter(source__owner=self.request.user).select_related(
            "source"
        )


class CommitmentUpdateView(
    LoginRequiredMixin, OwnedCommitmentMixin, CommitmentFormMixin, UpdateView
):
    model = Commitment


class CommitmentDeleteView(LoginRequiredMixin, OwnedCommitmentMixin, DeleteView):
    model = Commitment
    template_name = "scheduling/commitment_confirm_delete.html"
    success_url = reverse_lazy("scheduling:commitment_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Commitment deleted.")
        return response
