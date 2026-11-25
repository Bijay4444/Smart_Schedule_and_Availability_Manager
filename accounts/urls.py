"""Expose social signup and provider flows without adding local signup/reset flows."""
from allauth.socialaccount import views
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .social_auth import provider_login

urlpatterns = [
    # Names expected by allauth; the existing login/logout routes retain precedence.
    path("login/", LoginView.as_view(redirect_authenticated_user=True), name="account_login"),
    path("logout/", LogoutView.as_view(), name="account_logout"),
    path("social/signup/", views.signup, name="socialaccount_signup"),
    path("social/login/cancelled/", views.login_cancelled, name="socialaccount_login_cancelled"),
    path("social/login/error/", views.login_error, name="socialaccount_login_error"),
]
for provider in ("google", "github"):
    urlpatterns += [
        path(f"{provider}/login/", provider_login, {"provider": provider}, name=f"{provider}_login"),
        path(f"{provider}/login/callback/", provider_login,
             {"provider": provider, "callback": True}, name=f"{provider}_callback"),
    ]
