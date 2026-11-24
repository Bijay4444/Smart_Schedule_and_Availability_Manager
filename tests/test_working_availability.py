from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from threading import Barrier

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection

from scheduling.availability import (
    availability_for_user, check_proposed_shift, weekly_availability_for_user,
)
from scheduling.intervals import Interval
from scheduling.models import (
    Commitment, OverrideInterval, WorkingDateOverride, WorkingScheduleRevision, WorkingWindow,
)
from scheduling.recurrence import (
    cancel_occurrence, create_series, end_series, reschedule_occurrence, revise_series,
)
from scheduling.services import archive_source
from scheduling.working_windows import (
    WindowSpec, remove_working_date_override, set_working_date_override,
    set_working_schedule, working_windows_for_user,
)


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("scheduling.working_windows.timezone.now", lambda: datetime(2026, 10, 26, 15, tzinfo=UTC))


@pytest.fixture
def interval(halifax_time):
    def make(start, end):
        return Interval(halifax_time(start), halifax_time(end))
    return make


def schedule(owner, *windows, effective_from=MONDAY):
    return set_working_schedule(owner=owner, effective_from=effective_from, windows=windows)


def read(owner, halifax_time, start="2026-10-26T00:00", end="2026-11-02T00:00"):
    return availability_for_user(owner=owner, starts_at=halifax_time(start), ends_at=halifax_time(end))


def series(owner, source, **changes):
    return create_series(**{
        "owner": owner, "source_id": source.pk, "title": "Class",
        "starts_on": MONDAY, "start_time": time(10), "end_time": time(12),
        "weekdays": [0], **changes,
    })


def test_acceptance_subtracts_class_and_protected_study(owner, source, halifax_time, interval):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    series(owner, source)
    Commitment.objects.create(
        source=source, title="Study", starts_at=halifax_time("2026-10-26T12:00"),
        ends_at=halifax_time("2026-10-26T14:00"),
    )
    result = read(owner, halifax_time)
    assert result.complete
    assert result.available == (
        interval("2026-10-26T08:00", "2026-10-26T10:00"),
        interval("2026-10-26T14:00", "2026-10-26T20:00"),
    )
    assert len(result.commitments) == 2


def test_no_windows_means_no_availability_and_no_work_on_unconfigured_day(owner, halifax_time):
    assert read(owner, halifax_time).available == ()
    schedule(owner, WindowSpec(1, time(8), time(20)))
    result = read(owner, halifax_time, end="2026-10-27T00:00")
    assert result.available == ()
    assert result.complete


def test_overlapping_duplicate_occupied_and_touching_intervals_are_merged(
    owner, source, halifax_time, interval
):
    schedule(owner, WindowSpec(0, time(8), time(15)), WindowSpec(0, time(10), time(20)))
    for start, end in [(9, 12), (9, 12), (11, 14), (14, 16)]:
        Commitment.objects.create(
            source=source, title="Occupied", starts_at=halifax_time(f"2026-10-26T{start:02}:00"),
            ends_at=halifax_time(f"2026-10-26T{end:02}:00"),
        )
    result = read(owner, halifax_time)
    assert result.working_windows == (interval("2026-10-26T08:00", "2026-10-26T20:00"),)
    assert result.available == (
        interval("2026-10-26T08:00", "2026-10-26T09:00"),
        interval("2026-10-26T16:00", "2026-10-26T20:00"),
    )


def test_multiple_windows_and_every_positive_gap_remain(owner, source, halifax_time, interval):
    schedule(owner, WindowSpec(0, time(8), time(12)), WindowSpec(0, time(14), time(20)))
    for start, end in [("08:00", "11:59"), ("14:01", "20:00")]:
        Commitment.objects.create(
            source=source, title="Occupied", starts_at=halifax_time(f"2026-10-26T{start}"),
            ends_at=halifax_time(f"2026-10-26T{end}"),
        )
    assert read(owner, halifax_time).available == (
        interval("2026-10-26T11:59", "2026-10-26T12:00"),
        interval("2026-10-26T14:00", "2026-10-26T14:01"),
    )


@pytest.mark.parametrize("recurring", [False, True])
def test_sunday_commitment_blocks_monday_in_both_week_queries(
    owner, source, halifax_time, interval, recurring
):
    schedule(owner, WindowSpec(6, time(20), time(8), 1), effective_from=date(2026, 10, 19))
    if recurring:
        series(owner, source, starts_on=date(2026, 10, 25), ends_on=date(2026, 10, 25),
               weekdays=[6], start_time=time(22), end_time=time(6), end_day_offset=1)
    else:
        Commitment.objects.create(
            source=source, title="Overnight", starts_at=halifax_time("2026-10-25T22:00"),
            ends_at=halifax_time("2026-10-26T06:00"),
        )
    previous = read(owner, halifax_time, "2026-10-19T00:00", "2026-10-26T00:00")
    current = read(owner, halifax_time)
    assert previous.available == (interval("2026-10-25T20:00", "2026-10-25T22:00"),)
    assert current.available[0] == interval("2026-10-26T06:00", "2026-10-26T08:00")
    assert len(previous.commitments) == len(current.commitments) == 1


def test_date_override_replaces_overnight_carry_in_and_own_windows(owner, halifax_time, interval):
    schedule(owner, WindowSpec(6, time(22), time(6), 1), WindowSpec(0, time(8), time(20)),
             effective_from=date(2026, 10, 19))
    override = set_working_date_override(owner=owner, local_date=MONDAY, intervals=[])
    assert read(owner, halifax_time, end="2026-10-27T00:00").available == ()
    replacement = set_working_date_override(
        owner=owner, local_date=MONDAY,
        intervals=[interval("2026-10-26T14:00", "2026-10-26T18:00")],
    )
    assert replacement.pk == override.pk
    assert read(owner, halifax_time, end="2026-10-27T00:00").available == (
        interval("2026-10-26T14:00", "2026-10-26T18:00"),
    )
    remove_working_date_override(owner=owner, override_id=override.pk)
    assert read(owner, halifax_time, end="2026-10-27T00:00").available == (
        interval("2026-10-26T00:00", "2026-10-26T06:00"),
        interval("2026-10-26T08:00", "2026-10-26T20:00"),
    )


def test_override_can_open_a_date_without_weekly_windows_and_still_subtracts_commitments(
    owner, commitment, halifax_time, interval
):
    set_working_date_override(owner=owner, local_date=MONDAY, intervals=[
        interval("2026-10-26T08:00", "2026-10-26T14:00"),
        interval("2026-10-26T12:00", "2026-10-26T20:00"),
    ])
    assert OverrideInterval.objects.count() == 1
    assert read(owner, halifax_time).available == (
        interval("2026-10-26T08:00", "2026-10-26T10:00"),
        interval("2026-10-26T12:00", "2026-10-26T20:00"),
    )


@pytest.mark.parametrize("start,end", [
    ("2026-10-25T23:59", "2026-10-26T01:00"),
    ("2026-10-26T23:00", "2026-10-27T00:01"),
])
def test_invalid_override_is_rejected_without_changing_previous(owner, interval, start, end):
    override = set_working_date_override(owner=owner, local_date=MONDAY, intervals=[
        interval("2026-10-26T08:00", "2026-10-26T12:00"),
    ])
    with pytest.raises(ValidationError):
        set_working_date_override(owner=owner, local_date=MONDAY, intervals=[interval(start, end)])
    assert override.intervals.get().ends_at == interval("2026-10-26T08:00", "2026-10-26T12:00").ends_at


def test_working_history_and_later_plans_with_explicit_overrides_are_preserved(
    owner, halifax_time, interval
):
    initial = schedule(owner, WindowSpec(0, time(8), time(12)))
    schedule(owner, WindowSpec(0, time(14), time(20)), effective_from=date(2026, 12, 7))
    override = set_working_date_override(owner=owner, local_date=date(2026, 11, 23), intervals=[])
    schedule(owner, WindowSpec(0, time(10), time(14)), effective_from=date(2026, 11, 16))
    latest = schedule(owner, WindowSpec(0, time(11), time(15)), effective_from=date(2026, 11, 16))
    initial.refresh_from_db()
    assert initial.effective_until == latest.effective_from
    assert WorkingScheduleRevision.objects.count() == 2
    assert WorkingDateOverride.objects.filter(pk=override.pk).exists()
    assert read(owner, halifax_time).available == (interval("2026-10-26T08:00", "2026-10-26T12:00"),)
    assert read(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00").available == (
        interval("2026-11-16T11:00", "2026-11-16T15:00"),
    )
    assert read(owner, halifax_time, "2026-11-23T00:00", "2026-11-30T00:00").available == ()


def test_overnight_from_previous_revision_survives_its_end_date(owner, halifax_time, interval):
    schedule(owner, WindowSpec(6, time(22), time(6), 1), effective_from=date(2026, 10, 19))
    schedule(owner, effective_from=MONDAY)
    assert read(owner, halifax_time).available == (interval("2026-10-26T00:00", "2026-10-26T06:00"),)


def test_initial_setup_may_be_past_but_later_edits_cannot_rewrite_past(owner):
    initial = schedule(owner, WindowSpec(0, time(8), time(12)), effective_from=date(2026, 10, 1))
    with pytest.raises(ValidationError):
        schedule(owner, effective_from=date(2026, 10, 19))
    assert WorkingScheduleRevision.objects.get().pk == initial.pk


@pytest.mark.parametrize("windows", [
    None, ["not a window"], [WindowSpec(7, time(8), time(12))],
    [WindowSpec(True, time(8), time(12))], [WindowSpec(0, time(12), time(12))],
    [WindowSpec(0, time(12), time(8))], [WindowSpec(0, time(8), time(12), 2)],
    [WindowSpec(0, time(8), time(12), True)], [WindowSpec(0, "08:00", time(12))],
    [WindowSpec(0, time(8, tzinfo=UTC), time(12))],
    [WindowSpec(0, time(8), time(12)), WindowSpec(0, time(8), time(12))],
])
def test_invalid_windows_do_not_destroy_existing_schedule(owner, windows):
    initial = schedule(owner, WindowSpec(0, time(8), time(12)))
    with pytest.raises(ValidationError):
        set_working_schedule(owner=owner, effective_from=MONDAY, windows=windows)
    assert WorkingScheduleRevision.objects.get().pk == initial.pk
    assert WorkingWindow.objects.count() == 1


def test_failed_child_write_rolls_back_closing_the_previous_revision(owner, monkeypatch):
    initial = schedule(owner, WindowSpec(0, time(8), time(12)))

    def fail(*args, **kwargs):
        raise RuntimeError("simulated child insert failure")

    monkeypatch.setattr(WorkingWindow.objects, "bulk_create", fail)
    with pytest.raises(RuntimeError):
        schedule(owner, WindowSpec(1, time(8), time(12)), effective_from=date(2026, 11, 16))
    initial.refresh_from_db()
    assert initial.effective_until is None
    assert WorkingScheduleRevision.objects.count() == 1


@pytest.mark.parametrize("start,end,available,conflicts,outside", [
    ("09:00", "11:00", False, 1, 0),
    ("20:00", "22:00", False, 0, 1),
    ("12:00", "20:00", True, 0, 0),
    ("08:00", "10:00", True, 0, 0),
    ("07:00", "11:00", False, 1, 1),
])
def test_proposed_shift_checks_conflicts_and_working_coverage_without_saving(
    owner, source, halifax_time, start, end, available, conflicts, outside
):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    series(owner, source)
    result = check_proposed_shift(
        owner=owner, starts_at=halifax_time(f"2026-10-26T{start}"),
        ends_at=halifax_time(f"2026-10-26T{end}"),
    )
    assert result.is_available is available
    assert len(result.conflicts) == conflicts
    assert len(result.outside_working_windows) == outside
    assert result.complete
    assert not Commitment.objects.exists()
    assert WorkingScheduleRevision.objects.count() == 1


def test_shift_must_fit_every_instant_even_between_multiple_windows(owner, halifax_time, interval):
    schedule(owner, WindowSpec(0, time(8), time(12)), WindowSpec(0, time(13), time(20)))
    result = check_proposed_shift(
        owner=owner, starts_at=halifax_time("2026-10-26T11:00"),
        ends_at=halifax_time("2026-10-26T14:00"),
    )
    assert not result.is_available
    assert result.outside_working_windows == (interval("2026-10-26T12:00", "2026-10-26T13:00"),)


def test_proposed_overnight_shift_can_cross_adjacent_windows_and_week_boundary(owner, halifax_time):
    schedule(owner, WindowSpec(6, time(22), time(0), 1), WindowSpec(0, time(0), time(6)),
             effective_from=date(2026, 10, 19))
    result = check_proposed_shift(
        owner=owner, starts_at=halifax_time("2026-10-25T22:00"),
        ends_at=halifax_time("2026-10-26T06:00"),
    )
    assert result.is_available


def test_override_allows_explicit_second_repeated_hour(owner, halifax_time):
    day = date(2026, 11, 1)
    start = halifax_time("2026-11-01T01:15").replace(fold=1)
    end = halifax_time("2026-11-01T01:45").replace(fold=1)
    set_working_date_override(owner=owner, local_date=day, intervals=[Interval(start, end)])
    result = check_proposed_shift(owner=owner, starts_at=start, ends_at=end)
    assert result.is_available
    first_hour = check_proposed_shift(owner=owner, starts_at=start.replace(fold=0), ends_at=end.replace(fold=0))
    assert not first_hour.is_available


def test_archived_sources_and_recurring_exceptions_affect_current_availability(
    owner, source, halifax_time, interval
):
    schedule(owner, WindowSpec(0, time(8), time(20)), WindowSpec(1, time(8), time(20)))
    rule = series(owner, source)
    reschedule_occurrence(
        owner=owner, series_id=rule.pk, original_start_date=MONDAY,
        replacement_source_id=source.pk, replacement_title="Moved class",
        starts_at=halifax_time("2026-10-27T14:00"), ends_at=halifax_time("2026-10-27T16:00"),
    )
    archive_source(owner=owner, source_id=source.pk)
    result = read(owner, halifax_time)
    assert result.available == (
        interval("2026-10-26T08:00", "2026-10-26T20:00"),
        interval("2026-10-27T08:00", "2026-10-27T14:00"),
        interval("2026-10-27T16:00", "2026-10-27T20:00"),
    )
    cancel_occurrence(owner=owner, series_id=rule.pk, original_start_date=MONDAY)
    assert len(read(owner, halifax_time).available) == 2


def test_recurring_future_changes_and_ending_are_used(owner, source, halifax_time, interval):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    rule = series(owner, source)
    revise_series(owner=owner, series_id=rule.pk, effective_from=date(2026, 11, 16),
                  title="New class", start_time=time(14), end_time=time(16), weekdays=[0])
    result = read(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00")
    assert result.available == (
        interval("2026-11-16T08:00", "2026-11-16T14:00"),
        interval("2026-11-16T16:00", "2026-11-16T20:00"),
    )
    end_series(owner=owner, series_id=rule.pk, ends_before=date(2026, 11, 16))
    assert read(owner, halifax_time, "2026-11-16T00:00", "2026-11-23T00:00").available == (
        interval("2026-11-16T08:00", "2026-11-16T20:00"),
    )


def test_other_users_windows_overrides_commitments_and_recurrences_stay_private(
    owner, other_owner, other_source, halifax_time, interval
):
    schedule(other_owner, WindowSpec(0, time(8), time(20)))
    override = set_working_date_override(owner=other_owner, local_date=MONDAY, intervals=[
        interval("2026-10-26T00:00", "2026-10-27T00:00"),
    ])
    series(other_owner, other_source)
    Commitment.objects.create(
        source=other_source, title="Private", starts_at=halifax_time("2026-10-26T08:00"),
        ends_at=halifax_time("2026-10-26T20:00"),
    )
    result = read(owner, halifax_time)
    assert result.available == result.working_windows == result.commitments == ()
    schedule(owner, WindowSpec(0, time(8), time(20)))
    result = read(owner, halifax_time)
    assert result.available == (interval("2026-10-26T08:00", "2026-10-26T20:00"),)
    with pytest.raises(PermissionDenied):
        remove_working_date_override(owner=owner, override_id=override.pk)
    assert WorkingDateOverride.objects.filter(pk=override.pk).exists()


@pytest.mark.parametrize("day,expected_hours", [(date(2026, 3, 7), 7), (date(2026, 10, 31), 9)])
def test_overnight_dst_uses_actual_elapsed_hours(owner, halifax_time, day, expected_hours):
    schedule(owner, WindowSpec(5, time(22), time(6), 1), effective_from=day)
    result = read(owner, halifax_time, f"{day}T00:00", f"{day + timedelta(days=2)}T00:00")
    assert result.complete
    assert (result.available[0].ends_at - result.available[0].starts_at).total_seconds() == expected_hours * 3600


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_full_date_override_accepts_next_midnight_across_dst(owner, interval, halifax_time, day, hours):
    item = interval(f"{day}T00:00", f"{day + timedelta(days=1)}T00:00")
    set_working_date_override(owner=owner, local_date=day, intervals=[item])
    result = read(owner, halifax_time, f"{day}T00:00", f"{day + timedelta(days=1)}T00:00")
    assert result.available == (item,)
    assert (item.ends_at - item.starts_at).total_seconds() == hours * 3600


@pytest.mark.parametrize("day,start,end,adjustment", [
    (date(2026, 3, 8), time(2, 15), time(4), "gap_shift_forward"),
    (date(2026, 11, 1), time(1, 15), time(2), "fold_first"),
])
def test_working_dst_choices_remain_visible(owner, halifax_time, day, start, end, adjustment):
    schedule(owner, WindowSpec(6, start, end), effective_from=day)
    result = read(owner, halifax_time, f"{day}T00:00", f"{day + timedelta(days=1)}T00:00")
    assert result.complete
    assert result.adjustments[0].start_resolution.adjustment == adjustment
    assert result.available


def test_invalid_working_resolution_withholds_date_until_explicit_override(
    owner, halifax_time, interval
):
    day = date(2026, 3, 8)
    schedule(owner, WindowSpec(6, time(2, 30), time(3)), WindowSpec(6, time(8), time(20)),
             effective_from=day)
    result = read(owner, halifax_time, "2026-03-08T00:00", "2026-03-09T00:00")
    assert not result.complete
    assert result.working_issues
    assert result.available == ()
    proposal = check_proposed_shift(owner=owner, starts_at=halifax_time("2026-03-08T09:00"),
                                    ends_at=halifax_time("2026-03-08T10:00"))
    assert not proposal.is_available
    set_working_date_override(owner=owner, local_date=day, intervals=[
        interval("2026-03-08T08:00", "2026-03-08T20:00"),
    ])
    resolved = read(owner, halifax_time, "2026-03-08T00:00", "2026-03-09T00:00")
    assert resolved.complete
    assert resolved.available == (interval("2026-03-08T08:00", "2026-03-08T20:00"),)


def test_commitment_review_withholds_date_even_with_working_override_until_cancelled(
    owner, source, halifax_time, interval
):
    day = date(2026, 3, 8)
    rule = series(owner, source, starts_on=day, ends_on=day, weekdays=[6],
                  start_time=time(2, 30), end_time=time(3))
    set_working_date_override(owner=owner, local_date=day, intervals=[
        interval("2026-03-08T08:00", "2026-03-08T20:00"),
    ])
    result = weekly_availability_for_user(owner=owner, anchor=day)
    assert not result.complete
    assert result.days[6].intervals == ()
    assert not result.days[6].complete
    assert all(item.complete for item in result.days[:6])
    cancel_occurrence(owner=owner, series_id=rule.pk, original_start_date=day)
    assert weekly_availability_for_user(owner=owner, anchor=day).complete


def test_weekly_result_splits_overnight_hours_by_local_date(owner, interval):
    schedule(owner, WindowSpec(0, time(22), time(6), 1))
    result = weekly_availability_for_user(owner=owner, anchor=date(2026, 10, 29))
    assert result.starts_on == MONDAY
    assert len(result.days) == 7
    assert result.days[0].intervals == (interval("2026-10-26T22:00", "2026-10-27T00:00"),)
    assert result.days[1].intervals == (interval("2026-10-27T00:00", "2026-10-27T06:00"),)
    assert all(not item.intervals for item in result.days[2:])


@pytest.mark.parametrize("value", [None, "2026-10-26", datetime(2026, 10, 26), date.min, date.max])
def test_calendar_dates_are_validated_at_service_boundaries(owner, value):
    with pytest.raises(ValidationError):
        set_working_schedule(owner=owner, effective_from=value, windows=[])
    with pytest.raises(ValidationError):
        set_working_date_override(owner=owner, local_date=value, intervals=[])
    with pytest.raises(ValidationError):
        weekly_availability_for_user(owner=owner, anchor=value)


@pytest.mark.parametrize("value", [None, ["invalid interval"]])
def test_override_requires_explicit_aware_intervals(owner, value):
    with pytest.raises(ValidationError):
        set_working_date_override(owner=owner, local_date=MONDAY, intervals=value)
    assert not WorkingDateOverride.objects.exists()


def test_queries_clip_partial_windows_and_touching_commitments(owner, source, halifax_time, interval):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    series(owner, source)
    result = read(owner, halifax_time, "2026-10-26T12:00", "2026-10-26T13:00")
    assert result.available == (interval("2026-10-26T12:00", "2026-10-26T13:00"),)
    assert result.commitments == ()


@pytest.mark.parametrize("start,end", [
    (datetime(2026, 10, 26), datetime(2026, 10, 27)),
    (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC)),
    (datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 10, 25, tzinfo=UTC)),
    (datetime(2026, 1, 1, tzinfo=UTC), datetime(2028, 1, 1, tzinfo=UTC)),
    (datetime(1, 1, 1, tzinfo=UTC), datetime(1, 1, 2, tzinfo=UTC)),
])
def test_invalid_query_bounds_rejected_by_all_entry_points(owner, start, end):
    for service in (availability_for_user, working_windows_for_user, check_proposed_shift):
        with pytest.raises(ValidationError):
            service(owner=owner, starts_at=start, ends_at=end)


def test_query_count_is_bounded_across_windows_and_overrides(
    owner, source, halifax_time, interval, django_assert_max_num_queries
):
    schedule(owner, *(WindowSpec(day, time(hour), time(hour + 1))
                      for day in range(7) for hour in (8, 10, 14)))
    for offset in range(7):
        day = MONDAY + timedelta(days=offset)
        set_working_date_override(owner=owner, local_date=day, intervals=[
            interval(f"{day}T08:00", f"{day}T20:00"),
        ])
    for _ in range(5):
        series(owner, source)
    with django_assert_max_num_queries(10):
        result = read(owner, halifax_time)
    assert result.complete
    assert len(result.available) == 8


@pytest.mark.django_db(transaction=True)
def test_concurrent_initial_schedules_serialize_on_the_owner(owner):
    barrier = Barrier(2)

    def write(hour):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            barrier.wait(timeout=10)
            return schedule(owner, WindowSpec(0, time(hour), time(hour + 1))).pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(write, [8, 10]))
    assert WorkingScheduleRevision.objects.count() == 1
    assert WorkingWindow.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_overrides_keep_one_complete_date(owner, interval):
    barrier = Barrier(2)

    def write(hour):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            barrier.wait(timeout=10)
            return set_working_date_override(owner=owner, local_date=MONDAY, intervals=[
                interval(f"2026-10-26T{hour:02}:00", f"2026-10-26T{hour + 1:02}:00"),
            ]).pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(write, [8, 10]))
    assert ids[0] == ids[1]
    assert WorkingDateOverride.objects.count() == OverrideInterval.objects.count() == 1
