from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import OperationalError, close_old_connections, connection, transaction
from django.urls import reverse

from scheduling.availability import availability_for_user
from scheduling.conflicts import inspect_conflicts
from scheduling.models import Commitment, CommitmentSource
from scheduling.recurrence import (
    cancel_occurrence, create_series, end_series, reschedule_occurrence, revise_series,
)
from scheduling.services import (
    ConflictingCommitments, archive_source, commitments_for_user, save_commitment,
)


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("scheduling.recurrence.timezone.now", lambda: datetime(2026, 10, 26, 15, tzinfo=UTC))


@pytest.fixture
def make_series(owner, source):
    def make(**changes):
        return create_series(**{
            "owner": owner, "source_id": source.pk, "title": "Weekly class",
            "starts_on": MONDAY, "start_time": time(10), "end_time": time(12),
            "weekdays": [0], **changes,
        })
    return make


@pytest.fixture
def candidate(source, halifax_time):
    return Commitment(
        source=source, title="Offered shift", starts_at=halifax_time("2026-10-26T11:00"),
        ends_at=halifax_time("2026-10-26T13:00"),
    )


def inspect(owner, candidate):
    return inspect_conflicts(owner=owner, starts_at=candidate.starts_at, ends_at=candidate.ends_at,
                             exclude_pk=candidate.pk)


def move(owner, rule, source, halifax_time, original=MONDAY, **changes):
    return reschedule_occurrence(**{
        "owner": owner, "series_id": rule.pk, "original_start_date": original,
        "replacement_source_id": source.pk, "replacement_title": "Moved class",
        "starts_at": halifax_time("2026-10-27T14:00"),
        "ends_at": halifax_time("2026-10-27T16:00"), **changes,
    })


def test_save_warns_about_recurring_class_then_allows_explicit_confirmation(
    owner, candidate, make_series
):
    rule = make_series()
    with pytest.raises(ConflictingCommitments) as error:
        save_commitment(owner=owner, commitment=candidate)
    assert not Commitment.objects.exists()
    assert error.value.conflicts[0].key == (rule.pk, MONDAY)
    assert error.value.conflicts[0].title == "Weekly class"
    assert not error.value.issues
    save_commitment(owner=owner, commitment=candidate, confirm_conflicts=True)
    assert Commitment.objects.get().pk == candidate.pk
    assert commitments_for_user(owner=owner)[0].has_conflict


def test_failed_edit_preserves_stored_record_and_excludes_only_its_one_time_identity(
    owner, candidate, make_series, halifax_time
):
    rule = make_series()
    # One-time and series primary keys are independent namespaces.
    candidate.pk = rule.pk
    candidate.starts_at = halifax_time("2026-10-26T14:00")
    candidate.ends_at = halifax_time("2026-10-26T16:00")
    candidate.save(force_insert=True)
    candidate.starts_at = halifax_time("2026-10-26T11:00")
    candidate.ends_at = halifax_time("2026-10-26T13:00")
    with pytest.raises(ConflictingCommitments) as error:
        save_commitment(owner=owner, commitment=candidate)
    assert error.value.conflicts[0].series_id == candidate.pk
    candidate.refresh_from_db()
    assert candidate.starts_at == halifax_time("2026-10-26T14:00")


@pytest.mark.parametrize("start,end", [("08:00", "10:00"), ("12:00", "14:00")])
def test_recurring_touching_boundaries_do_not_warn(owner, candidate, make_series, halifax_time, start, end):
    make_series()
    candidate.starts_at = halifax_time(f"2026-10-26T{start}")
    candidate.ends_at = halifax_time(f"2026-10-26T{end}")
    save_commitment(owner=owner, commitment=candidate)
    item = commitments_for_user(owner=owner)[0]
    assert not item.has_conflict
    assert item.conflict_check_complete


def test_query_returns_one_time_and_recurring_conflicts_in_time_order(
    owner, candidate, commitment, make_series
):
    make_series(start_time=time(9), end_time=time(12))
    result = inspect(owner, candidate)
    assert result.complete
    assert [item.title for item in result.conflicts] == ["Weekly class", commitment.title]
    assert not candidate.pk
    assert Commitment.objects.count() == 1


def test_cancelled_or_rescheduled_out_occurrence_no_longer_conflicts(
    owner, candidate, make_series, source, halifax_time
):
    rule = make_series()
    move(owner, rule, source, halifax_time)
    assert inspect(owner, candidate).conflicts == ()
    cancel_occurrence(owner=owner, series_id=rule.pk, original_start_date=MONDAY)
    save_commitment(owner=owner, commitment=candidate)
    assert not commitments_for_user(owner=owner)[0].has_conflict


def test_replacement_moved_in_from_old_series_is_found(owner, candidate, make_series, source, halifax_time):
    old = date(2025, 10, 27)
    rule = make_series(starts_on=old, ends_on=old)
    move(owner, rule, source, halifax_time, original=old,
         starts_at=candidate.starts_at, ends_at=candidate.ends_at)
    result = inspect(owner, candidate)
    assert len(result.conflicts) == 1
    assert result.conflicts[0].is_replacement
    assert result.conflicts[0].original_start_date == old


def test_explicit_replacement_survives_future_edit_then_obeys_ending_cutoff(
    owner, candidate, make_series, source, halifax_time
):
    original = date(2026, 11, 16)
    rule = make_series()
    move(owner, rule, source, halifax_time, original=original,
         starts_at=candidate.starts_at, ends_at=candidate.ends_at)
    revise_series(owner=owner, series_id=rule.pk, effective_from=original, title="Changed class",
                  start_time=time(14), end_time=time(16), weekdays=[1])
    assert len(inspect(owner, candidate).conflicts) == 2
    end_series(owner=owner, series_id=rule.pk, ends_before=original)
    assert len(inspect(owner, candidate).conflicts) == 1


def test_future_revision_is_used_on_its_effective_date(owner, candidate, make_series, halifax_time):
    rule = make_series()
    revise_series(owner=owner, series_id=rule.pk, effective_from=date(2026, 11, 16),
                  title="Evening class", start_time=time(18), end_time=time(20), weekdays=[0])
    candidate.starts_at = halifax_time("2026-11-16T11:00")
    candidate.ends_at = halifax_time("2026-11-16T13:00")
    assert not inspect(owner, candidate).conflicts
    candidate.starts_at = halifax_time("2026-11-16T19:00")
    candidate.ends_at = halifax_time("2026-11-16T21:00")
    assert inspect(owner, candidate).conflicts[0].title == "Evening class"


def test_final_sunday_overnight_occurrence_conflicts_with_monday(
    owner, candidate, make_series, halifax_time
):
    make_series(starts_on=date(2026, 10, 25), ends_on=date(2026, 10, 25), weekdays=[6],
                start_time=time(22), end_time=time(6), end_day_offset=1)
    candidate.starts_at = halifax_time("2026-10-26T05:00")
    candidate.ends_at = halifax_time("2026-10-26T07:00")
    with pytest.raises(ConflictingCommitments):
        save_commitment(owner=owner, commitment=candidate)


def test_archived_series_and_replacement_sources_still_warn(
    owner, candidate, make_series, source, halifax_time
):
    rule = make_series()
    replacement_source = CommitmentSource.objects.create(owner=owner, name="Former classes")
    move(owner, rule, replacement_source, halifax_time, original=date(2026, 11, 2),
         starts_at=candidate.starts_at, ends_at=candidate.ends_at)
    archive_source(owner=owner, source_id=source.pk)
    archive_source(owner=owner, source_id=replacement_source.pk)
    candidate.source = CommitmentSource.objects.create(owner=owner, name="Current job")
    with pytest.raises(ConflictingCommitments) as error:
        save_commitment(owner=owner, commitment=candidate)
    assert {item.source_id if isinstance(item, Commitment) else item.source.pk
            for item in error.value.conflicts} == {source.pk, replacement_source.pk}


def test_foreign_recurring_commitments_and_issues_never_appear(
    owner, candidate, make_series, other_owner, other_source, halifax_time
):
    make_series(owner=other_owner, source_id=other_source.pk)
    assert inspect(owner, candidate).conflicts == ()
    make_series(owner=other_owner, source_id=other_source.pk, starts_on=date(2026, 3, 8),
                ends_on=date(2026, 3, 8), weekdays=[6], start_time=time(2, 30), end_time=time(3))
    candidate.starts_at = halifax_time("2026-03-08T10:00")
    candidate.ends_at = halifax_time("2026-03-08T12:00")
    assert inspect(owner, candidate).complete
    save_commitment(owner=owner, commitment=candidate)
    item = commitments_for_user(owner=owner)[0]
    assert not item.has_conflict
    assert item.conflict_check_complete


def test_dst_invalid_date_requires_warning_and_stays_incomplete_after_acknowledgement(
    owner, candidate, make_series, halifax_time
):
    rule = make_series(starts_on=date(2026, 3, 8), ends_on=date(2026, 3, 8), weekdays=[6],
                       start_time=time(2, 30), end_time=time(3))
    candidate.starts_at = halifax_time("2026-03-08T10:00")
    candidate.ends_at = halifax_time("2026-03-08T12:00")
    with pytest.raises(ConflictingCommitments) as error:
        save_commitment(owner=owner, commitment=candidate)
    assert error.value.conflicts == []
    assert error.value.issues[0].series_id == rule.pk
    assert not candidate.pk
    save_commitment(owner=owner, commitment=candidate, confirm_conflicts=True)
    item = commitments_for_user(owner=owner)[0]
    assert not item.has_conflict
    assert not item.conflict_check_complete
    result = availability_for_user(owner=owner, starts_at=candidate.starts_at, ends_at=candidate.ends_at)
    assert not result.complete
    cancel_occurrence(owner=owner, series_id=rule.pk, original_start_date=date(2026, 3, 8))
    assert commitments_for_user(owner=owner)[0].conflict_check_complete


def test_review_on_other_dates_does_not_block_a_valid_save(owner, candidate, make_series):
    make_series(starts_on=date(2026, 3, 8), ends_on=date(2026, 3, 8), weekdays=[6],
                start_time=time(2, 30), end_time=time(3))
    save_commitment(owner=owner, commitment=candidate)
    assert commitments_for_user(owner=owner)[0].conflict_check_complete


def test_batched_list_issues_do_not_mark_unaffected_dates_incomplete(owner, source, make_series, halifax_time):
    make_series(starts_on=date(2026, 3, 8), ends_on=date(2026, 3, 8), weekdays=[6],
                start_time=time(2, 30), end_time=time(3))
    for day in ("2026-03-02", "2026-03-09"):
        Commitment.objects.create(source=source, title="Valid date", starts_at=halifax_time(f"{day}T10:00"),
                                  ends_at=halifax_time(f"{day}T12:00"))
    items = commitments_for_user(owner=owner)
    assert all(item.conflict_check_complete for item in items)
    assert all(not item.has_conflict for item in items)


def test_clock_choices_use_actual_instants_in_repeated_hour(owner, candidate, make_series, halifax_time):
    make_series(starts_on=date(2026, 11, 1), ends_on=date(2026, 11, 1), weekdays=[6],
                start_time=time(1, 15), end_time=time(1, 45))
    candidate.starts_at = halifax_time("2026-11-01T01:20").replace(fold=1)
    candidate.ends_at = halifax_time("2026-11-01T01:40").replace(fold=1)
    assert not inspect(owner, candidate).conflicts
    save_commitment(owner=owner, commitment=candidate)
    candidate.starts_at = candidate.starts_at.replace(fold=0)
    candidate.ends_at = candidate.ends_at.replace(fold=0)
    assert inspect(owner, candidate).conflicts


def test_long_one_time_interval_is_checked_fully_and_chunk_duplicates_are_removed(
    owner, candidate, make_series, halifax_time
):
    make_series(starts_on=date(2027, 1, 1), ends_on=date(2027, 1, 1), weekdays=[4],
                start_time=time(22), end_time=time(6), end_day_offset=1)
    make_series(starts_on=date(2027, 12, 6), ends_on=date(2027, 12, 6))
    candidate.starts_at = halifax_time("2026-01-01T00:00")
    candidate.ends_at = halifax_time("2028-01-01T00:00")
    result = inspect(owner, candidate)
    assert len(result.conflicts) == 2
    assert len({item.key for item in result.conflicts}) == 2
    with pytest.raises(ConflictingCommitments):
        save_commitment(owner=owner, commitment=candidate)


def test_list_checks_many_one_time_rows_with_a_bounded_query_count(
    owner, source, make_series, halifax_time, django_assert_max_num_queries
):
    for _ in range(6):
        make_series()
    Commitment.objects.bulk_create([
        Commitment(source=source, title=f"Shift {index}",
                   starts_at=halifax_time("2026-10-26T11:00"), ends_at=halifax_time("2026-10-26T13:00"))
        for index in range(20)
    ])
    with django_assert_max_num_queries(6):
        items = commitments_for_user(owner=owner)
    assert len(items) == 20
    assert all(item.has_conflict and item.conflict_check_complete for item in items)


def test_saved_indicators_follow_cancellation_and_rescheduling(
    owner, candidate, make_series, source, halifax_time
):
    rule = make_series()
    save_commitment(owner=owner, commitment=candidate, confirm_conflicts=True)
    assert commitments_for_user(owner=owner)[0].has_conflict
    move(owner, rule, source, halifax_time)
    assert not commitments_for_user(owner=owner)[0].has_conflict
    cancel_occurrence(owner=owner, series_id=rule.pk, original_start_date=MONDAY)
    assert not commitments_for_user(owner=owner)[0].has_conflict


@pytest.mark.parametrize("start,end", [
    (datetime(2026, 10, 26), datetime(2026, 10, 27)),
    (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC)),
    (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 25, tzinfo=UTC)),
    (datetime(1, 1, 1, tzinfo=UTC), datetime(1, 1, 2, tzinfo=UTC)),
])
def test_invalid_conflict_query_returns_validation_error(owner, start, end):
    with pytest.raises(ValidationError):
        inspect_conflicts(owner=owner, starts_at=start, ends_at=end)


def test_legacy_calendar_limit_rows_remain_readable_with_review_flag(owner, source):
    Commitment.objects.create(source=source, title="Extreme date",
                              starts_at=datetime(1, 1, 2, tzinfo=UTC),
                              ends_at=datetime(1, 1, 3, tzinfo=UTC))
    item = commitments_for_user(owner=owner)[0]
    assert not item.conflict_check_complete


def test_browser_warning_confirmation_and_list_include_recurring_conflicts(
    client, owner, make_series, commitment_data
):
    make_series()
    client.force_login(owner)
    data = {**commitment_data, "starts_at": "2026-10-26T11:00", "ends_at": "2026-10-26T13:00"}
    response = client.post(reverse("scheduling:commitment_create"), data)
    assert response.status_code == 200
    assert b"This overlaps your existing commitments" in response.content
    assert b"Weekly class" in response.content
    assert not Commitment.objects.exists()
    response = client.post(reverse("scheduling:commitment_create"), {**data, "confirm_conflicts": "on"},
                           follow=True)
    assert response.status_code == 200
    assert b"Overlaps another commitment" in response.content
    assert Commitment.objects.count() == 1


def test_browser_conflicting_edit_requires_confirmation(client, owner, candidate, make_series, commitment_data):
    make_series()
    candidate.save()
    client.force_login(owner)
    url = reverse("scheduling:commitment_update", args=[candidate.pk])
    data = {**commitment_data, "title": "Changed title", "starts_at": "2026-10-26T11:00",
            "ends_at": "2026-10-26T13:00"}
    response = client.post(url, data)
    assert response.status_code == 200
    candidate.refresh_from_db()
    assert candidate.title == "Offered shift"
    response = client.post(url, {**data, "confirm_conflicts": "on"})
    assert response.status_code == 302
    candidate.refresh_from_db()
    assert candidate.title == "Changed title"


def test_browser_shows_review_only_warning_and_keeps_it_visible_after_save(
    client, owner, make_series, commitment_data
):
    make_series(starts_on=date(2026, 3, 8), ends_on=date(2026, 3, 8), weekdays=[6],
                start_time=time(2, 30), end_time=time(3))
    client.force_login(owner)
    data = {**commitment_data, "starts_at": "2026-03-08T10:00", "ends_at": "2026-03-08T12:00"}
    response = client.post(reverse("scheduling:commitment_create"), data)
    assert response.status_code == 200
    assert b"Conflict check needs review" in response.content
    assert b"Weekly class" in response.content
    assert b"confirm_conflicts" in response.content
    assert not Commitment.objects.exists()
    response = client.post(reverse("scheduling:commitment_create"), {**data, "confirm_conflicts": "on"},
                           follow=True)
    assert response.status_code == 200
    assert b"Conflict check needs review" in response.content
    assert b"Overlaps another commitment" not in response.content


def test_browser_warning_never_discloses_foreign_series(client, owner, make_series, other_owner,
                                                       other_source, commitment_data):
    make_series(owner=other_owner, source_id=other_source.pk, title="Confidential class")
    client.force_login(owner)
    data = {**commitment_data, "starts_at": "2026-10-26T11:00", "ends_at": "2026-10-26T13:00"}
    response = client.post(reverse("scheduling:commitment_create"), data, follow=True)
    assert response.status_code == 200
    assert b"Confidential class" not in response.content
    assert b"Overlaps another commitment" not in response.content


@pytest.mark.django_db(transaction=True)
def test_concurrent_one_time_saves_on_different_sources_cannot_both_miss_warning(
    owner, source, halifax_time
):
    other_source = CommitmentSource.objects.create(owner=owner, name="Another job")
    barrier = Barrier(2)

    def write(source_id):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            barrier.wait(timeout=10)
            item = Commitment(source_id=source_id, title="Competing shift",
                              starts_at=halifax_time("2026-10-26T11:00"),
                              ends_at=halifax_time("2026-10-26T13:00"))
            try:
                save_commitment(owner=owner, commitment=item)
            except ConflictingCommitments:
                return "warned"
            return "saved"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(write, [source.pk, other_source.pk])) == ["saved", "warned"]
    assert Commitment.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_recurring_creation_holds_the_same_owner_lock_until_commit(owner, source, candidate, make_series):
    candidate.source = CommitmentSource.objects.create(owner=owner, name="Another source")

    def try_save():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '500ms'")
                cursor.execute("SET statement_timeout = '5s'")
            try:
                save_commitment(owner=owner, commitment=candidate)
            except OperationalError as error:
                return error.__cause__.sqlstate
            return "unexpectedly saved"
        finally:
            connection.close()

    with transaction.atomic():
        make_series()
        # The series is uncommitted and its source differs from the candidate's.
        # Only the shared owner lock can prevent an incomplete preflight here.
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(try_save).result(timeout=10) == "55P03"
    with pytest.raises(ConflictingCommitments):
        save_commitment(owner=owner, commitment=candidate)
    assert not Commitment.objects.exists()
