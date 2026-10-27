import pytest
from django.core.exceptions import PermissionDenied

from scheduling.models import Commitment
from scheduling.services import (
    ConflictingCommitments,
    commitments_for_user,
    find_conflicts,
    save_commitment,
)


pytestmark = pytest.mark.django_db


def test_save_requires_confirmation_for_overlaps(owner, source, commitment, halifax_time):
    candidate = Commitment(
        source=source,
        title="Offered shift",
        starts_at=halifax_time("2026-10-26T11:00"),
        ends_at=halifax_time("2026-10-26T13:00"),
    )

    with pytest.raises(ConflictingCommitments) as error:
        save_commitment(commitment=candidate, owner=owner)
    assert error.value.conflicts == [commitment]
    assert Commitment.objects.count() == 1

    saved = save_commitment(commitment=candidate, owner=owner, confirm_conflicts=True)
    assert saved.pk
    assert Commitment.objects.count() == 2


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-10-26T08:00", "2026-10-26T10:00"),
        ("2026-10-26T12:00", "2026-10-26T14:00"),
    ],
)
def test_touching_boundaries_do_not_conflict(
    owner, source, commitment, halifax_time, start, end
):
    candidate = Commitment(
        source=source,
        title="Adjacent shift",
        starts_at=halifax_time(start),
        ends_at=halifax_time(end),
    )

    save_commitment(commitment=candidate, owner=owner)

    assert candidate.pk


def test_overnight_conflict_crosses_a_week_boundary(owner, source, halifax_time):
    overnight = Commitment.objects.create(
        source=source,
        title="Sunday night shift",
        starts_at=halifax_time("2026-10-25T22:00"),
        ends_at=halifax_time("2026-10-26T06:00"),
    )

    conflicts = find_conflicts(
        owner=owner,
        starts_at=halifax_time("2026-10-26T05:30"),
        ends_at=halifax_time("2026-10-26T07:00"),
    )

    assert list(conflicts) == [overnight]


def test_update_does_not_conflict_with_itself(owner, commitment):
    commitment.title = "Updated shift"

    save_commitment(commitment=commitment, owner=owner)

    commitment.refresh_from_db()
    assert commitment.title == "Updated shift"
    assert Commitment.objects.count() == 1


def test_service_rejects_foreign_source(owner, other_source, halifax_time):
    candidate = Commitment(
        source=other_source,
        title="Not mine",
        starts_at=halifax_time("2026-10-26T10:00"),
        ends_at=halifax_time("2026-10-26T12:00"),
    )

    with pytest.raises(PermissionDenied):
        save_commitment(commitment=candidate, owner=owner)
    assert not Commitment.objects.exists()


def test_service_cannot_reassign_another_users_commitment(
    owner, source, other_source, halifax_time
):
    foreign = Commitment.objects.create(
        source=other_source,
        title="Private shift",
        starts_at=halifax_time("2026-10-26T10:00"),
        ends_at=halifax_time("2026-10-26T12:00"),
    )
    foreign.source = source

    with pytest.raises(PermissionDenied):
        save_commitment(commitment=foreign, owner=owner)
    foreign.refresh_from_db()
    assert foreign.source == other_source


def test_conflict_indicators_are_symmetric_and_private(
    owner, source, commitment, other_source, halifax_time
):
    Commitment.objects.create(
        source=other_source,
        title="Private overlapping shift",
        starts_at=commitment.starts_at,
        ends_at=commitment.ends_at,
    )
    assert not list(commitments_for_user(owner=owner))[0].has_conflict

    second = Commitment.objects.create(
        source=source,
        title="Own overlapping shift",
        starts_at=halifax_time("2026-10-26T11:00"),
        ends_at=halifax_time("2026-10-26T13:00"),
    )
    items = list(commitments_for_user(owner=owner))

    assert {item.pk for item in items} == {commitment.pk, second.pk}
    assert all(item.has_conflict for item in items)
