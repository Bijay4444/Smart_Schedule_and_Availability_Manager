import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from scheduling.forms import CommitmentForm
from scheduling.models import Commitment, CommitmentSource
from scheduling.services import archive_source, commitments_for_user, find_conflicts, save_commitment


pytestmark = pytest.mark.django_db


def test_archival_is_idempotent_and_preserves_occupied_time(owner, commitment):
    archived = archive_source(source_id=commitment.source_id, owner=owner)
    timestamp = archived.archived_at
    archived_again = archive_source(source_id=archived.pk, owner=owner)

    assert timestamp is not None
    assert archived_again.archived_at == timestamp
    assert list(commitments_for_user(owner=owner)) == [commitment]
    assert list(find_conflicts(
        owner=owner, starts_at=commitment.starts_at, ends_at=commitment.ends_at
    )) == [commitment]
    with pytest.raises(ProtectedError):
        archived.delete()
    assert Commitment.objects.filter(pk=commitment.pk).exists()


def test_cannot_archive_another_users_source(owner, other_source):
    with pytest.raises(PermissionDenied):
        archive_source(source_id=other_source.pk, owner=owner)
    other_source.refresh_from_db()
    assert other_source.archived_at is None


def test_archived_choices_hidden_but_existing_source_can_be_kept(owner, commitment):
    archive_source(source_id=commitment.source_id, owner=owner)
    assert not CommitmentForm(owner=owner).fields["source"].queryset.exists()
    edit = CommitmentForm(owner=owner, instance=commitment)
    assert list(edit.fields["source"].queryset) == [commitment.source]


def test_service_checks_stored_archive_state_even_with_stale_source(owner, source, halifax_time):
    archive_source(source_id=source.pk, owner=owner)
    candidate = Commitment(
        source=source, title="New assignment",
        starts_at=halifax_time("2026-10-26T10:00"),
        ends_at=halifax_time("2026-10-26T12:00"),
    )
    assert source.archived_at is None  # Caller fetched this before archival.
    with pytest.raises(ValidationError, match="active source"):
        save_commitment(commitment=candidate, owner=owner)
    assert not Commitment.objects.exists()


def test_existing_commitment_can_keep_archived_source_but_cannot_switch_to_one(
    owner, commitment
):
    archive_source(source_id=commitment.source_id, owner=owner)
    commitment.title = "Corrected past entry"
    save_commitment(commitment=commitment, owner=owner)
    commitment.refresh_from_db()
    assert commitment.title == "Corrected past entry"

    retired = CommitmentSource.objects.create(owner=owner, name="Retired job")
    archive_source(source_id=retired.pk, owner=owner)
    commitment.source = retired
    with pytest.raises(ValidationError, match="active source"):
        save_commitment(commitment=commitment, owner=owner)
    commitment.refresh_from_db()
    assert commitment.source_id != retired.pk


def test_browser_allows_editing_archived_commitment_and_rejects_new_assignment(
    client, owner, commitment, commitment_data
):
    archive_source(source_id=commitment.source_id, owner=owner)
    client.force_login(owner)
    response = client.post(reverse("scheduling:commitment_create"), commitment_data)
    assert response.status_code == 200
    assert "source" in response.context["form"].errors

    response = client.post(
        reverse("scheduling:commitment_update", args=[commitment.pk]),
        {**commitment_data, "title": "Corrected entry"},
    )
    assert response.status_code == 302
    commitment.refresh_from_db()
    assert commitment.title == "Corrected entry"


def test_archive_between_form_validation_and_save_is_a_field_error(
    client, owner, source, commitment_data, monkeypatch
):
    from scheduling import views

    original_save = views.save_commitment

    def archive_then_save(**kwargs):
        archive_source(source_id=source.pk, owner=owner)
        return original_save(**kwargs)

    monkeypatch.setattr(views, "save_commitment", archive_then_save)
    client.force_login(owner)
    response = client.post(reverse("scheduling:commitment_create"), commitment_data)
    assert response.status_code == 200
    assert "source" in response.context["form"].errors
    assert not Commitment.objects.exists()
