"""Small HTTP/configuration boundary around allauth's OAuth implementation."""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods


def provider_enabled(provider):
    app = settings.SOCIALACCOUNT_PROVIDERS.get(provider, {}).get("APP", {})
    return bool(app.get("client_id") and app.get("secret"))


def social_providers(request):
    return {"social_providers": [
        {"id": provider, "label": label, "login_url": f"{provider}_login"}
        for provider, label in (("google", "Google"), ("github", "GitHub"))
        if provider_enabled(provider)
    ]}


@require_http_methods(["GET", "POST"])
def provider_login(request, provider, callback=False):
    if not provider_enabled(provider):
        messages.info(request, "That sign-in provider is not available yet. Please use another sign-in method.")
        return redirect("login")
    # allauth validates OAuth state and performs code exchange and identity lookup.
    if provider == "google":
        from allauth.socialaccount.providers.google import views
    else:
        from allauth.socialaccount.providers.github import views
    view = views.oauth2_callback if callback else views.oauth2_login
    return view(request)
