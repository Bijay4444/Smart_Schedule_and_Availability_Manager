from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

from core.views import HomeView, healthz


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("", HomeView.as_view(), name="home"),
    path("", include("scheduling.urls")),
    path("", include("assistant.urls")),
]
