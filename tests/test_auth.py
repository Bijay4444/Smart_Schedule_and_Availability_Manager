import pytest
from django.test import Client
from django.urls import reverse


pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="student", password="test-password-only", first_name="Student"
    )


def test_home_requires_login(client):
    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert response.url == reverse("login") + "?next=/"


def test_login_page_renders_a_csrf_protected_form(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert b'name="csrfmiddlewaretoken"' in response.content
    assert b'autocomplete="current-password"' in response.content


def test_valid_login_opens_the_authenticated_home(client, user):
    response = client.post(
        reverse("login"),
        {"username": user.username, "password": "test-password-only"},
        follow=True,
    )

    assert response.redirect_chain == [(reverse("home"), 302)]
    assert response.status_code == 200
    assert response.context["user"] == user
    assert b"Welcome, Student." in response.content
    assert b"Sign out" in response.content


def test_invalid_password_keeps_the_user_signed_out(client, user):
    response = client.post(
        reverse("login"), {"username": user.username, "password": "wrong-password"}
    )

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert not response.context["user"].is_authenticated
    assert client.get(reverse("home")).status_code == 302


def test_inactive_user_cannot_sign_in(client, user):
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = client.post(
        reverse("login"),
        {"username": user.username, "password": "test-password-only"},
    )

    assert response.status_code == 200
    assert not response.context["user"].is_authenticated


def test_login_does_not_redirect_to_an_external_site(client, user):
    response = client.post(
        reverse("login"),
        {
            "username": user.username,
            "password": "test-password-only",
            "next": "https://example.org/",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("home")


def test_post_logout_ends_the_session(client, user):
    client.force_login(user)

    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")
    assert client.get(reverse("home")).status_code == 302


def test_get_logout_does_not_end_the_session(client, user):
    client.force_login(user)

    assert client.get(reverse("logout")).status_code == 405
    assert client.get(reverse("home")).status_code == 200


def test_login_and_logout_require_valid_csrf_tokens(user):
    client = Client(enforce_csrf_checks=True)
    credentials = {"username": user.username, "password": "test-password-only"}

    assert client.post(reverse("login"), credentials).status_code == 403
    client.get(reverse("login"))
    response = client.post(
        reverse("login"),
        {**credentials, "csrfmiddlewaretoken": client.cookies["csrftoken"].value},
    )
    assert response.status_code == 302
    assert client.get(reverse("home")).status_code == 200

    assert client.post(reverse("logout")).status_code == 403
    response = client.post(
        reverse("logout"),
        {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
    )
    assert response.status_code == 302
    assert client.get(reverse("home")).status_code == 302
