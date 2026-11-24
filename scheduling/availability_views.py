from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.views.generic import TemplateView

from .availability_presentation import availability_screen_for_user
from .calendar import calendar_date


class WeeklyAvailabilityView(LoginRequiredMixin, TemplateView):
    template_name = "scheduling/availability.html"

    def get(self, request, *args, **kwargs):
        try:
            anchor = calendar_date(request.GET["week"]) if "week" in request.GET else None
            screen = availability_screen_for_user(owner=request.user, anchor=anchor)
        except ValidationError as error:
            return HttpResponseBadRequest(" ".join(error.messages))
        response = self.render_to_response(self.get_context_data(availability=screen))
        # Availability is private and recalculated for each request, including
        # when a user returns to this week after changing their schedule.
        response["Cache-Control"] = "private, no-store"
        return response
