from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.views.generic.edit import FormView

from .calendar import calendar_date
from .shift_forms import ProposedShiftForm
from .shift_presentation import shift_screen_for_user


class ProposedShiftView(LoginRequiredMixin, FormView):
    template_name = "scheduling/proposed_shift.html"
    form_class = ProposedShiftForm
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except ValidationError as error:
            return HttpResponseBadRequest(" ".join(error.messages))

    def get_initial(self):
        initial = super().get_initial()
        if self.request.method in ("GET", "HEAD") and "date" in self.request.GET:
            day = calendar_date(self.request.GET["date"])
            initial = {"starts_at": f"{day.isoformat()}T09:00", "ends_at": f"{day.isoformat()}T17:00"}
        return initial

    def form_valid(self, form):
        try:
            result = shift_screen_for_user(owner=self.request.user,
                                           starts_at=form.cleaned_data["starts_at"],
                                           ends_at=form.cleaned_data["ends_at"])
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        return self.render_to_response(self.get_context_data(form=form, result=result))

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
