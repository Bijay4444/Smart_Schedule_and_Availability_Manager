import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from scheduling.models import Commitment, CommitmentSource


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "route",
    ["commitment_list", "commitment_create", "source_create", "commitment_update", "commitment_delete"],
)
def test_scheduling_routes_require_login(client, commitment, route):
    kwargs = {"pk": commitment.pk} if route in {"commitment_update", "commitment_delete"} else {}

    response = client.get(reverse(f"scheduling:{route}", kwargs=kwargs))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login") + "?next=")


def test_empty_schedule_explains_the_first_step(client, owner):
    client.force_login(owner)

    response = client.get(reverse("scheduling:commitment_list"))

    assert response.status_code == 200
    assert b"Add your first source" in response.content


def test_list_only_shows_the_signed_in_users_commitments(
    client, owner, commitment, other_source
):
    foreign = Commitment.objects.create(
        source=other_source,
        title="Confidential appointment",
        starts_at=commitment.starts_at,
        ends_at=commitment.ends_at,
    )
    client.force_login(owner)

    response = client.get(reverse("scheduling:commitment_list"))

    assert response.status_code == 200
    assert list(response.context["commitments"]) == [commitment]
    assert commitment.title.encode() in response.content
    assert foreign.title.encode() not in response.content
    assert other_source.name.encode() not in response.content
    assert b"Overlaps another commitment" not in response.content
    assert commitment.source.color.encode() in response.content


def test_source_creation_sets_owner_from_the_session(client, owner, other_owner):
    client.force_login(owner)

    response = client.post(
        reverse("scheduling:source_create"),
        {"name": "Classes", "color": "#456789", "owner": other_owner.pk},
    )

    assert response.status_code == 302
    source = CommitmentSource.objects.get()
    assert source.owner == owner
    assert source.name == "Classes"
    assert source.color == "#456789"


def test_duplicate_source_is_a_form_error(client, owner, source):
    client.force_login(owner)

    response = client.post(
        reverse("scheduling:source_create"),
        {"name": source.name, "color": "#456789"},
    )

    assert response.status_code == 200
    assert "name" in response.context["form"].errors
    assert CommitmentSource.objects.count() == 1


def test_create_one_time_commitment(client, owner, commitment_data):
    client.force_login(owner)

    response = client.post(reverse("scheduling:commitment_create"), commitment_data)

    assert response.status_code == 302
    assert response.url == reverse("scheduling:commitment_list")
    commitment = Commitment.objects.get()
    assert commitment.title == "Evening shift"
    assert commitment.source.owner == owner


def test_create_overnight_commitment(client, owner, commitment_data):
    client.force_login(owner)

    response = client.post(
        reverse("scheduling:commitment_create"),
        {**commitment_data, "starts_at": "2026-10-25T22:00", "ends_at": "2026-10-26T06:00"},
        follow=True,
    )

    assert response.status_code == 200
    assert Commitment.objects.count() == 1
    assert b"Sun 25 Oct 2026, 22:00" in response.content
    assert b"Mon 26 Oct 2026, 06:00" in response.content


def test_create_rejects_forged_foreign_source(client, owner, other_source, commitment_data):
    client.force_login(owner)

    response = client.post(
        reverse("scheduling:commitment_create"),
        {**commitment_data, "source": other_source.pk},
    )

    assert response.status_code == 200
    assert "source" in response.context["form"].errors
    assert not Commitment.objects.exists()


def test_overlap_requires_confirmation_and_stays_visible_after_saving(
    client, owner, commitment, commitment_data
):
    client.force_login(owner)
    data = {**commitment_data, "starts_at": "2026-10-26T11:00", "ends_at": "2026-10-26T13:00"}

    response = client.post(reverse("scheduling:commitment_create"), data)

    assert response.status_code == 200
    assert b"This overlaps your existing commitments" in response.content
    assert commitment.title.encode() in response.content
    assert Commitment.objects.count() == 1

    response = client.post(
        reverse("scheduling:commitment_create"),
        {**data, "confirm_conflicts": "on"},
        follow=True,
    )

    assert response.status_code == 200
    assert Commitment.objects.count() == 2
    assert response.content.count(b"Overlaps another commitment") == 2


def test_edit_own_commitment(client, owner, commitment, commitment_data):
    client.force_login(owner)

    response = client.post(
        reverse("scheduling:commitment_update", args=[commitment.pk]),
        {**commitment_data, "title": "Updated shift"},
    )

    assert response.status_code == 302
    commitment.refresh_from_db()
    assert commitment.title == "Updated shift"


def test_conflicting_edit_is_not_saved_until_confirmed(
    client, owner, commitment, source, halifax_time, commitment_data
):
    target = Commitment.objects.create(
        source=source,
        title="Afternoon shift",
        starts_at=halifax_time("2026-10-26T14:00"),
        ends_at=halifax_time("2026-10-26T16:00"),
    )
    client.force_login(owner)
    data = {**commitment_data, "title": "Edited afternoon shift", "starts_at": "2026-10-26T11:00", "ends_at": "2026-10-26T13:00"}

    response = client.post(reverse("scheduling:commitment_update", args=[target.pk]), data)

    assert response.status_code == 200
    assert b"This overlaps your existing commitments" in response.content
    target.refresh_from_db()
    assert target.title == "Afternoon shift"
    assert target.starts_at == halifax_time("2026-10-26T14:00")


@pytest.mark.parametrize("route", ["commitment_update", "commitment_delete"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_another_users_object_routes_are_not_accessible(
    client, other_owner, commitment, commitment_data, route, method
):
    client.force_login(other_owner)

    response = getattr(client, method)(
        reverse(f"scheduling:{route}", args=[commitment.pk]), commitment_data
    )

    assert response.status_code == 404
    commitment.refresh_from_db()
    assert commitment.title == "Morning shift"


def test_deletion_requires_a_post_confirmation(client, owner, commitment):
    client.force_login(owner)
    url = reverse("scheduling:commitment_delete", args=[commitment.pk])

    response = client.get(url)
    assert response.status_code == 200
    assert b"Delete this commitment?" in response.content
    assert Commitment.objects.filter(pk=commitment.pk).exists()

    response = client.post(url)
    assert response.status_code == 302
    assert not Commitment.objects.filter(pk=commitment.pk).exists()


@pytest.mark.parametrize("action", ["commitment_create", "commitment_update", "commitment_delete", "source_create"])
def test_scheduling_writes_require_csrf(owner, commitment, commitment_data, action):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    args = [commitment.pk] if action in {"commitment_update", "commitment_delete"} else []

    response = client.post(reverse(f"scheduling:{action}", args=args), commitment_data)

    assert response.status_code == 403
    assert Commitment.objects.count() == 1
    assert CommitmentSource.objects.count() == 1


def test_admin_is_read_only_for_commitments(client, owner, commitment):
    owner.is_staff = True
    owner.is_superuser = True
    owner.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(owner)

    assert client.get(reverse("admin:scheduling_commitment_changelist")).status_code == 200
    assert client.get(reverse("admin:scheduling_commitment_add")).status_code == 403
    assert client.post(
        reverse("admin:scheduling_commitment_delete", args=[commitment.pk]),
        {"post": "yes"},
    ).status_code == 403
    assert Commitment.objects.filter(pk=commitment.pk).exists()


def test_staff_admin_cannot_inspect_another_users_commitment(
    client, owner, other_source, halifax_time
):
    foreign = Commitment.objects.create(
        source=other_source,
        title="Private shift",
        starts_at=halifax_time("2026-10-26T10:00"),
        ends_at=halifax_time("2026-10-26T12:00"),
    )
    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    owner.user_permissions.add(
        Permission.objects.get(codename="view_commitment", content_type__app_label="scheduling")
    )
    client.force_login(owner)

    response = client.get(reverse("admin:scheduling_commitment_changelist"))
    assert response.status_code == 200
    assert foreign.title.encode() not in response.content

    response = client.get(reverse("admin:scheduling_commitment_change", args=[foreign.pk]))
    assert foreign.title.encode() not in response.content
    assert response.status_code in {302, 404}
