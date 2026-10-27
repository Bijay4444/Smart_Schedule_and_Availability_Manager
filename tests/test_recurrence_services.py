from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from threading import Barrier

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.utils import timezone

from scheduling.models import OccurrenceException, RecurringSeries, RevisionWeekday, SeriesRevision
from scheduling.recurrence import (
    cancel_occurrence, create_series, end_series, occurrences_for_user,
    reschedule_occurrence, revise_series,
)
from scheduling.services import archive_source


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("scheduling.recurrence.timezone.now", lambda: datetime(2026, 10, 26, 15, tzinfo=UTC))


@pytest.fixture
def make_series(owner, source):
    def make(**changes):
        return create_series(**{
            "owner": owner, "source_id": source.pk, "title": "Morning class",
            "starts_on": date(2026, 10, 26), "start_time": time(9), "end_time": time(11),
            "weekdays": [0, 2], **changes,
        })
    return make


def change_series(owner, series, **changes):
    return revise_series(**{
        "owner": owner, "series_id": series.pk, "effective_from": date(2026, 11, 16),
        "title": "Revised class", "start_time": time(10), "end_time": time(12),
        "weekdays": [0, 2], **changes,
    })


def query(owner, halifax_time, start="2026-10-26T00:00", end="2026-11-02T00:00"):
    return occurrences_for_user(owner=owner, starts_at=halifax_time(start), ends_at=halifax_time(end))


def move(owner, series, source, halifax_time, original=date(2026, 11, 16), **changes):
    return reschedule_occurrence(**{
        "owner": owner, "series_id": series.pk, "original_start_date": original,
        "replacement_source_id": source.pk, "replacement_title": "Moved class",
        "starts_at": halifax_time("2026-11-17T13:00"),
        "ends_at": halifax_time("2026-11-17T15:00"), **changes,
    })


def test_create_series_saves_one_complete_rule_with_inclusive_end(make_series):
    series = make_series(ends_on=date(2026, 12, 6), weekdays=[6, 0])
    revision = series.revisions.get()
    assert series.ends_before == date(2026, 12, 7)
    assert revision.effective_from == series.starts_on
    assert list(revision.weekdays.values_list("weekday", flat=True)) == [0, 6]
    assert (revision.dst_gap_policy, revision.dst_fold_policy) == ("shift_forward", "first")


@pytest.mark.parametrize("changes", [
    {"weekdays": []}, {"weekdays": None}, {"weekdays": [0, 0]}, {"weekdays": [7]}, {"weekdays": [True]},
    {"ends_on": date(2026, 10, 25)}, {"time_zone": "Not/AZone"},
    {"end_time": time(8)}, {"end_day_offset": 2}, {"title": ""},
    {"start_time": time(9, tzinfo=UTC)},
    {"start_time": "invalid clock"}, {"end_time": None},
])
def test_invalid_creation_rolls_back_parent_and_all_children(make_series, changes):
    with pytest.raises(ValidationError):
        make_series(**changes)
    assert not RecurringSeries.objects.exists()
    assert not SeriesRevision.objects.exists()
    assert not RevisionWeekday.objects.exists()


def test_creation_requires_owned_active_source(make_series, owner, source, other_source):
    with pytest.raises(PermissionDenied):
        make_series(source_id=other_source.pk)
    archive_source(source_id=source.pk, owner=owner)
    with pytest.raises(ValidationError):
        make_series()
    assert not RecurringSeries.objects.exists()


def test_occurrences_are_bounded_selected_weekdays_and_not_saved(make_series, owner, halifax_time):
    series = make_series(ends_on=date(2026, 11, 2))
    result = query(owner, halifax_time, "2026-10-25T00:00", "2026-11-04T00:00")
    assert result.complete
    assert [item.original_start_date for item in result.occurrences] == [
        date(2026, 10, 26), date(2026, 10, 28), date(2026, 11, 2)
    ]
    assert result.occurrences[0].key == (series.pk, date(2026, 10, 26))
    assert result.occurrences[0].starts_at.tzinfo == UTC
    assert series.revisions.count() == 1
    assert series.exceptions.count() == 0


def test_final_overnight_occurrence_appears_in_both_weeks(make_series, owner, halifax_time):
    make_series(
        starts_on=date(2026, 10, 25), ends_on=date(2026, 10, 25), weekdays=[6],
        start_time=time(22), end_time=time(6), end_day_offset=1,
    )
    previous = query(owner, halifax_time, "2026-10-19T00:00", "2026-10-26T00:00")
    current = query(owner, halifax_time)
    assert len(previous.occurrences) == len(current.occurrences) == 1
    assert previous.occurrences[0].key == current.occurrences[0].key
    assert current.occurrences[0].ends_at == halifax_time("2026-10-26T06:00")
    assert not query(owner, halifax_time, "2026-11-01T00:00", "2026-11-02T00:00").occurrences


@pytest.mark.parametrize("start,end", [
    ("2026-10-26T07:00", "2026-10-26T09:00"),
    ("2026-10-26T11:00", "2026-10-26T12:00"),
])
def test_touching_query_boundaries_do_not_overlap(make_series, owner, halifax_time, start, end):
    make_series()
    assert not query(owner, halifax_time, start, end).occurrences


def test_future_revision_preserves_earlier_weeks_and_changes_all_selected_days(
    make_series, owner, halifax_time
):
    series = make_series()
    original = series.revisions.get()
    successor = change_series(owner, series, weekdays=[1, 3])
    original.refresh_from_db()
    assert original.effective_until == date(2026, 11, 16)
    assert original.start_time == time(9)
    assert successor.dst_gap_policy == original.dst_gap_policy
    past = query(owner, halifax_time, "2026-11-09T00:00", "2026-11-16T00:00")
    future = query(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00")
    assert [item.original_start_date.day for item in past.occurrences] == [9, 11]
    assert [item.original_start_date.day for item in future.occurrences] == [17, 19]
    assert all(item.title == "Revised class" for item in future.occurrences)
    assert all(item.starts_at == halifax_time(f"2026-11-{item.original_start_date.day}T10:00") for item in future.occurrences)


def test_all_future_edit_supersedes_later_plans_and_same_date_can_be_corrected(make_series, owner):
    series = make_series()
    original = series.revisions.get()
    change_series(owner, series, effective_from=date(2026, 12, 7))
    change_series(owner, series, effective_from=date(2026, 11, 16))
    latest = change_series(owner, series, effective_from=date(2026, 11, 16), title="Corrected plan")
    assert series.revisions.count() == 2
    original.refresh_from_db()
    assert original.title == "Morning class"
    assert original.effective_until == latest.effective_from
    assert latest.effective_until is None


@pytest.mark.parametrize("changes", [
    {"effective_from": date(2026, 10, 25)}, {"weekdays": []},
    {"end_time": time(8)}, {"title": ""},
    {"start_time": "invalid clock"},
])
def test_invalid_future_edit_leaves_existing_rule_unchanged(make_series, owner, changes):
    series = make_series()
    original = series.revisions.get()
    with pytest.raises(ValidationError):
        change_series(owner, series, **changes)
    original.refresh_from_db()
    assert original.effective_until is None
    assert series.revisions.count() == 1


def test_exception_survives_pattern_change_and_can_still_be_edited(
    make_series, owner, source, halifax_time
):
    series = make_series()
    replacement = move(owner, series, source, halifax_time)
    change_series(owner, series, weekdays=[2])  # Monday no longer selected.
    result = query(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00")
    assert [item.title for item in result.occurrences] == ["Moved class", "Revised class"]
    moved_again = move(owner, series, source, halifax_time, replacement_title="Moved again")
    assert moved_again.pk == replacement.pk
    assert moved_again.original_start_date == date(2026, 11, 16)


def test_move_to_another_week_suppresses_original_and_includes_actual_week(
    make_series, owner, source, halifax_time
):
    series = make_series(weekdays=[0])
    move(owner, series, source, halifax_time,
         starts_at=halifax_time("2026-11-24T13:00"), ends_at=halifax_time("2026-11-24T15:00"))
    assert not query(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00").occurrences
    result = query(owner, halifax_time, "2026-11-24T00:00", "2026-11-25T00:00")
    assert len(result.occurrences) == 1
    assert result.occurrences[0].original_start_date == date(2026, 11, 16)
    assert result.occurrences[0].is_replacement


def test_replacement_found_even_when_series_lifetime_is_outside_query(
    make_series, owner, source, halifax_time
):
    series = make_series(ends_on=date(2026, 10, 26))
    move(owner, series, source, halifax_time, original=date(2026, 10, 26),
         starts_at=halifax_time("2027-05-04T13:00"), ends_at=halifax_time("2027-05-04T15:00"))
    result = query(owner, halifax_time, "2027-05-04T00:00", "2027-05-05T00:00")
    assert len(result.occurrences) == 1
    assert result.occurrences[0].series_id == series.pk


def test_cancel_only_one_occurrence_and_can_replace_previous_reschedule(
    make_series, owner, source, halifax_time
):
    series = make_series()
    replacement = move(owner, series, source, halifax_time)
    cancelled = cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=date(2026, 11, 16))
    assert cancelled.pk == replacement.pk
    assert cancelled.starts_at is None and cancelled.replacement_source_id is None
    result = query(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00")
    assert [item.original_start_date.day for item in result.occurrences] == [18]
    assert len(query(owner, halifax_time, "2026-11-23T00:00", "2026-11-30T00:00").occurrences) == 2


def test_end_series_uses_original_start_date_for_moved_replacements(
    make_series, owner, source, halifax_time
):
    series = make_series()
    move(owner, series, source, halifax_time)
    end_series(owner=owner, series_id=series.pk, ends_before=date(2026, 11, 16))
    assert not query(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00").occurrences
    assert series.exceptions.count() == 1  # Preserved, but inactive.
    assert len(query(owner, halifax_time, "2026-11-09T00:00", "2026-11-16T00:00").occurrences) == 2


def test_end_retains_replacement_with_earlier_original_date_and_final_overnight(
    make_series, owner, source, halifax_time
):
    series = make_series(starts_on=date(2026, 10, 25), weekdays=[6], start_time=time(22), end_time=time(6), end_day_offset=1)
    end_series(owner=owner, series_id=series.pk, ends_before=date(2026, 10, 26))
    assert len(query(owner, halifax_time).occurrences) == 1

    another = make_series(weekdays=[0])
    move(owner, another, source, halifax_time, original=date(2026, 10, 26))
    end_series(owner=owner, series_id=another.pk, ends_before=date(2026, 11, 2))
    result = query(owner, halifax_time, "2026-11-17T00:00", "2026-11-18T00:00")
    assert len(result.occurrences) == 1
    assert result.occurrences[0].original_start_date == date(2026, 10, 26)


def test_ending_before_series_start_creates_empty_lifetime_and_never_reopens(make_series, owner, halifax_time):
    series = make_series(starts_on=date(2026, 11, 16))
    ended = end_series(owner=owner, series_id=series.pk, ends_before=date(2026, 10, 27))
    assert ended.ends_before == series.starts_on
    end_series(owner=owner, series_id=series.pk, ends_before=date(2026, 12, 7))
    assert not query(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00").occurrences


@pytest.mark.parametrize("original", [date(2026, 10, 25), date(2026, 11, 17), date(2027, 1, 4)])
def test_new_exception_must_target_actual_original_occurrence(make_series, owner, original):
    series = make_series(ends_on=date(2026, 12, 6))
    with pytest.raises(ValidationError):
        cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=original)
    assert not OccurrenceException.objects.exists()


def test_archival_preserves_series_and_allows_correction_with_original_source(
    make_series, owner, source, halifax_time
):
    series = make_series()
    archive_source(source_id=source.pk, owner=owner)
    assert len(query(owner, halifax_time).occurrences) == 2
    move(owner, series, source, halifax_time)
    change_series(owner, series)
    assert series.exceptions.count() == 1


def test_cross_owner_reads_and_writes_are_private(make_series, owner, other_owner, other_source, source, halifax_time):
    series = make_series()
    assert not query(other_owner, halifax_time).occurrences
    for action in [
        lambda: change_series(other_owner, series),
        lambda: end_series(owner=other_owner, series_id=series.pk, ends_before=date(2026, 11, 16)),
        lambda: cancel_occurrence(owner=other_owner, series_id=series.pk, original_start_date=date(2026, 11, 16)),
        lambda: move(owner, series, other_source, halifax_time),
        lambda: move(other_owner, series, other_source, halifax_time),
    ]:
        with pytest.raises(PermissionDenied):
            action()
    assert not OccurrenceException.objects.exists()


def test_explicit_second_fold_replacement_compares_instants_in_utc(make_series, owner, source, halifax_time):
    series = make_series(weekdays=[6])
    move(owner, series, source, halifax_time, original=date(2026, 11, 1),
         starts_at=halifax_time("2026-11-01T01:45").replace(fold=0),
         ends_at=halifax_time("2026-11-01T01:15").replace(fold=1))
    result = query(owner, halifax_time, "2026-11-01T00:00", "2026-11-02T00:00")
    assert result.occurrences[0].ends_at - result.occurrences[0].starts_at == timedelta(minutes=30)


@pytest.mark.parametrize("day,expected_hours", [(date(2026, 3, 7), 7), (date(2026, 10, 31), 9)])
def test_overnight_dst_elapsed_hours_differ_from_local_clock_labels(make_series, owner, halifax_time, day, expected_hours):
    make_series(starts_on=day, ends_on=day, weekdays=[5], start_time=time(22), end_time=time(6), end_day_offset=1)
    result = query(owner, halifax_time, f"{day}T00:00", f"{day + timedelta(days=2)}T00:00")
    occurrence = result.occurrences[0]
    assert occurrence.ends_at - occurrence.starts_at == timedelta(hours=expected_hours)
    assert occurrence.start_resolution.value.hour == 22
    assert occurrence.end_resolution.value.hour == 6


def test_gap_and_fold_metadata_and_normal_local_clocks(make_series, owner, halifax_time):
    make_series(starts_on=date(2026, 3, 1), weekdays=[6], start_time=time(2, 30), end_time=time(4))
    gap = query(owner, halifax_time, "2026-03-08T00:00", "2026-03-09T00:00").occurrences[0]
    following = query(owner, halifax_time, "2026-03-15T00:00", "2026-03-16T00:00").occurrences[0]
    assert gap.start_resolution.adjustment == "gap_shift_forward"
    assert following.start_resolution.value.hour == 2
    assert following.start_resolution.adjustment is None
    make_series(weekdays=[6], start_time=time(1, 30), end_time=time(2))
    fall = query(owner, halifax_time, "2026-11-01T00:00", "2026-11-02T00:00")
    assert any(item.start_resolution.adjustment == "fold_first" for item in fall.occurrences)


@pytest.mark.parametrize("end_time", [time(3), time(3, 30)])
def test_invalid_dst_interval_marks_day_incomplete_and_exception_resolves_it(make_series, owner, source, halifax_time, end_time):
    series = make_series(starts_on=date(2026, 3, 1), weekdays=[6], start_time=time(2, 30), end_time=end_time)
    result = query(owner, halifax_time, "2026-03-08T00:00", "2026-03-09T00:00")
    assert not result.complete
    assert not result.occurrences
    assert result.issues[0].original_start_date == date(2026, 3, 8)
    assert query(owner, halifax_time, "2026-03-09T00:00", "2026-03-10T00:00").complete
    move(owner, series, source, halifax_time, original=date(2026, 3, 8),
         starts_at=halifax_time("2026-03-08T04:00"), ends_at=halifax_time("2026-03-08T05:00"))
    repaired = query(owner, halifax_time, "2026-03-08T00:00", "2026-03-09T00:00")
    assert repaired.complete and len(repaired.occurrences) == 1


def test_display_zone_change_does_not_reinterpret_stored_rules(make_series, owner, halifax_time):
    make_series()
    before = query(owner, halifax_time)
    with timezone.override("Asia/Tokyo"):
        after = query(owner, halifax_time)
    assert before == after


def test_failed_edit_after_closing_old_revision_rolls_back_every_change(make_series, owner, monkeypatch):
    series = make_series()
    original = series.revisions.get()

    def failing_insert(*args, **kwargs):
        raise RuntimeError("Simulated interrupted write")

    monkeypatch.setattr(RevisionWeekday.objects, "bulk_create", failing_insert)
    with pytest.raises(RuntimeError, match="interrupted write"):
        change_series(owner, series)
    original.refresh_from_db()
    assert original.effective_until is None
    assert series.revisions.count() == 1
    assert list(original.weekdays.values_list("weekday", flat=True)) == [0, 2]


def test_cancellation_survives_later_changes_and_repeated_cancellation_is_safe(make_series, owner, halifax_time):
    series = make_series()
    cancelled = cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=date(2026, 11, 16))
    change_series(owner, series, weekdays=[2])
    repeated = cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=date(2026, 11, 16))
    assert cancelled.pk == repeated.pk
    assert [item.original_start_date.day for item in query(
        owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00"
    ).occurrences] == [18]


def test_new_archived_replacement_source_rejected_and_invalid_instants_do_not_save(
    make_series, owner, source, halifax_time
):
    from scheduling.models import CommitmentSource

    series = make_series()
    archived = CommitmentSource.objects.create(owner=owner, name="Retired second job")
    archive_source(source_id=archived.pk, owner=owner)
    with pytest.raises(ValidationError):
        move(owner, series, archived, halifax_time)
    with pytest.raises(ValidationError):
        move(owner, series, source, halifax_time, starts_at=datetime(2026, 11, 17, 13))
    with pytest.raises(ValidationError):
        move(owner, series, source, halifax_time, starts_at="invalid instant")
    with pytest.raises(ValidationError):
        move(owner, series, source, halifax_time, ends_at=halifax_time("2026-11-17T12:00"))
    assert not series.exceptions.exists()


def test_future_rules_cannot_modify_past_or_extend_an_ended_lifetime(make_series, owner):
    series = make_series(starts_on=date(2026, 10, 1), ends_on=date(2026, 11, 1))
    with pytest.raises(ValidationError):
        change_series(owner, series, effective_from=date(2026, 10, 19))
    with pytest.raises(ValidationError):
        change_series(owner, series, effective_from=date(2026, 11, 2))
    with pytest.raises(ValidationError):
        end_series(owner=owner, series_id=series.pk, ends_before=date(2026, 10, 19))
    series.refresh_from_db()
    assert series.ends_before == date(2026, 11, 2)


def test_skipped_date_occurrence_is_found_on_resolved_day(make_series, owner):
    series = make_series(
        time_zone="Pacific/Apia", starts_on=date(2011, 12, 30), ends_on=date(2011, 12, 30), weekdays=[4]
    )
    result = occurrences_for_user(
        owner=owner, starts_at=datetime(2011, 12, 30, 10, tzinfo=UTC),
        ends_at=datetime(2011, 12, 31, 10, tzinfo=UTC),
    )
    assert result.complete
    assert [item.key for item in result.occurrences] == [(series.pk, date(2011, 12, 30))]
    assert result.occurrences[0].start_resolution.value.date() == date(2011, 12, 31)


def test_expansion_near_calendar_limit_does_not_overflow_weekday_iteration(make_series, owner):
    day = date(9999, 12, 26)
    make_series(starts_on=day, weekdays=[day.weekday()], time_zone="UTC")
    result = occurrences_for_user(
        owner=owner, starts_at=datetime(9999, 12, 26, tzinfo=UTC),
        ends_at=datetime(9999, 12, 27, tzinfo=UTC),
    )
    assert len(result.occurrences) == 1


def test_query_count_stays_bounded_with_multiple_series_and_revisions(
    make_series, owner, halifax_time, django_assert_max_num_queries
):
    for _ in range(6):
        series = make_series()
        change_series(owner, series)
    with django_assert_max_num_queries(5):
        result = query(owner, halifax_time, "2026-11-09T00:00", "2026-11-23T00:00")
    assert len(result.occurrences) == 24


@pytest.mark.parametrize("start,end", [
    (datetime(2026, 10, 26), datetime(2026, 10, 27)),
    (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC)),
    (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 25, tzinfo=UTC)),
    (datetime(2026, 1, 1, tzinfo=UTC), datetime(2028, 1, 1, tzinfo=UTC)),
])
def test_query_rejects_naive_reversed_empty_or_excessive_range(owner, start, end):
    with pytest.raises(ValidationError):
        occurrences_for_user(owner=owner, starts_at=start, ends_at=end)


@pytest.mark.django_db(transaction=True)
def test_concurrent_future_edits_serialize_without_losing_earlier_rule(make_series, owner):
    series = make_series()
    barrier = Barrier(2)

    def change(at):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            barrier.wait(timeout=10)
            return change_series(owner, series, effective_from=at).pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(change, [date(2026, 11, 16), date(2026, 11, 23)]))
    revisions = list(series.revisions.order_by("effective_from"))
    assert revisions[0].title == "Morning class"
    assert revisions[0].effective_until == date(2026, 11, 16)
    for left, right in zip(revisions, revisions[1:]):
        assert left.effective_until == right.effective_from
    assert revisions[-1].effective_until is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_cancellations_create_one_exception_with_stable_identity(make_series, owner):
    series = make_series()
    barrier = Barrier(2)

    def cancel(_):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            barrier.wait(timeout=10)
            return cancel_occurrence(
                owner=owner, series_id=series.pk, original_start_date=date(2026, 11, 16)
            ).pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(cancel, range(2)))
    assert ids[0] == ids[1]
    assert series.exceptions.count() == 1
