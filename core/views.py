from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import HttpResponse
from django.views.decorators.http import require_safe


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "core/home.html"


@require_safe
def healthz(request):
    """Process liveness only: no authentication, database access, or private data."""
    return HttpResponse("ok\n", content_type="text/plain", headers={"Cache-Control": "no-store"})
