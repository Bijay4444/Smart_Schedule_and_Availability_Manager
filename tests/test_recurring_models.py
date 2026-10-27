from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError

from scheduling.models import (
    OccurrenceException, RecurringSeries, RevisionWeekday, SeriesRevision,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def series(source):
    return RecurringSeries.objects.create(
        source=source, time_zone="America/Halifax", starts_on=date(2026, 10, 26)
    )


def revision_values(series, **changes):
    return {
        "series": series, "effective_from": date(2026, 10, 26),
        "title": "Morning class", "start_time": time(9), "end_time": time(11),
        **changes,
    }


def assert_db_rejects(model, constraint, **values):
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        model.objects.create(**values)
    assert error.value.__cause__.diag.constraint_name == constraint


def test_adjacent_revisions_preserve_history_and_open_end(series):
    first = SeriesRevision.objects.create(**revision_values(
        series, effective_until=date(2026, 11, 16)
    ))
    second = SeriesRevision.objects.create(**revision_values(
        series, effective_from=date(2026, 11, 16), start_time=time(10)
    ))
    first.refresh_from_db()
    assert first.start_time == time(9)
    assert first.effective_until == second.effective_from
    assert second.effective_until is None
    assert second.dst_gap_policy == "shift_forward"
    assert second.dst_fold_policy == "first"


@pytest.mark.parametrize("start,end", [
    (date(2026, 11, 1), None),
    (date(2026, 10, 25), date(2026, 10, 27)),
    (date(2026, 10, 26), date(2026, 10, 28)),
])
def test_overlapping_revision_periods_rejected_even_without_model_validation(series, start, end):
    SeriesRevision.objects.create(**revision_values(series))
    assert_db_rejects(
        SeriesRevision, "series_revision_periods_do_not_overlap",
        **revision_values(series, effective_from=start, effective_until=end),
    )


def test_different_series_can_have_overlapping_revision_periods(series, source):
    other = RecurringSeries.objects.create(
        source=source, time_zone="America/Halifax", starts_on=series.starts_on
    )
    SeriesRevision.objects.create(**revision_values(series))
    SeriesRevision.objects.create(**revision_values(other))
    assert SeriesRevision.objects.count() == 2


@pytest.mark.parametrize("changes,constraint", [
    ({"effective_until": date(2026, 10, 26)}, "revision_positive_date_period"),
    ({"end_day_offset": 2}, "revision_valid_day_offset"),
    ({"end_time": time(9)}, "revision_positive_local_interval"),
    ({"end_time": time(8)}, "revision_positive_local_interval"),
    ({"dst_gap_policy": "skip"}, "revision_valid_gap_policy"),
    ({"dst_fold_policy": "second"}, "revision_valid_fold_policy"),
])
def test_invalid_revision_rows_are_rejected(series, changes, constraint):
    assert_db_rejects(SeriesRevision, constraint, **revision_values(series, **changes))


def test_series_lifetime_may_be_empty_but_not_reversed(series):
    series.ends_before = series.starts_on
    series.full_clean()
    series.save()
    assert_db_rejects(
        RecurringSeries, "series_lifetime_not_reversed", source=series.source,
        time_zone=series.time_zone, starts_on=series.starts_on,
        ends_before=date(2026, 10, 25),
    )


def test_weekdays_are_unique_and_in_monday_to_sunday_range(series):
    revision = SeriesRevision.objects.create(**revision_values(series))
    RevisionWeekday.objects.create(revision=revision, weekday=0)
    RevisionWeekday.objects.create(revision=revision, weekday=6)
    assert_db_rejects(
        RevisionWeekday, "weekday_unique_per_revision", revision=revision, weekday=0
    )
    assert_db_rejects(
        RevisionWeekday, "revision_weekday_in_range", revision=revision, weekday=7
    )


def test_overnight_rule_stores_local_clocks_and_zone_without_resolving_instants(series):
    revision = SeriesRevision(**revision_values(
        series, start_time=time(22), end_time=time(6), end_day_offset=1
    ))
    revision.full_clean()
    revision.save()
    assert revision.end_day_offset == 1
    series.time_zone = "Not/AZone"
    with pytest.raises(ValidationError) as error:
        series.full_clean()
    assert "time_zone" in error.value.message_dict


def test_cancel_and_reschedule_keep_original_identity_across_revisions(series, source, halifax_time):
    revision = SeriesRevision.objects.create(**revision_values(
        series, effective_until=date(2026, 11, 16)
    ))
    replacement = OccurrenceException.objects.create(
        series=series, original_start_date=date(2026, 11, 2), kind="reschedule",
        replacement_source=source, replacement_title="Moved class",
        starts_at=halifax_time("2026-11-10T09:00"),
        ends_at=halifax_time("2026-11-10T11:00"),
    )
    cancellation = OccurrenceException.objects.create(
        series=series, original_start_date=date(2026, 11, 9), kind="cancel"
    )
    SeriesRevision.objects.create(**revision_values(
        series, effective_from=revision.effective_until, start_time=time(10)
    ))
    replacement.refresh_from_db()
    assert replacement.original_start_date == date(2026, 11, 2)
    assert replacement.series_id == series.pk
    assert replacement.starts_at == halifax_time("2026-11-10T09:00")
    assert_db_rejects(
        OccurrenceException, "exception_unique_per_original_date",
        series=series, original_start_date=cancellation.original_start_date, kind="cancel",
    )


@pytest.mark.parametrize("kind,payload", [
    ("cancel", {"replacement_title": "Unexpected payload"}),
    ("cancel", {"starts_at": "start"}),
    ("reschedule", {}),
    ("reschedule", {"replacement_title": ""}),
    ("reschedule", {"ends_at": "start"}),
    ("reschedule", {"replacement_source": None}),
    ("unknown", {}),
])
def test_exception_kind_requires_complete_positive_replacement_or_empty_cancellation(
    series, source, halifax_time, kind, payload
):
    start = halifax_time("2026-11-02T09:00")
    values = {"series": series, "original_start_date": series.starts_on, "kind": kind}
    if kind == "reschedule":
        values.update(
            replacement_source=source, replacement_title="Moved class",
            starts_at=start, ends_at=halifax_time("2026-11-02T11:00"),
        )
    values.update({key: start if value == "start" else value for key, value in payload.items()})
    # A completely missing replacement payload also needs to be rejected.
    if kind == "reschedule" and not payload:
        values = {"series": series, "original_start_date": series.starts_on, "kind": kind}
    assert_db_rejects(OccurrenceException, "exception_payload_matches_kind", **values)


def test_replacement_validation_rejects_cross_owner_and_naive_instants(
    series, other_source, halifax_time
):
    replacement = OccurrenceException(
        series=series, original_start_date=series.starts_on, kind="reschedule",
        replacement_source=other_source, replacement_title="Moved class",
        starts_at=halifax_time("2026-11-02T09:00").replace(tzinfo=None),
        ends_at=halifax_time("2026-11-02T11:00"),
    )
    with pytest.raises(ValidationError) as error:
        replacement.full_clean()
    assert {"replacement_source", "starts_at"} <= error.value.message_dict.keys()


def test_referenced_series_and_sources_protected_while_weekdays_follow_revision(series, source):
    revision = SeriesRevision.objects.create(**revision_values(series))
    RevisionWeekday.objects.create(revision=revision, weekday=0)
    with pytest.raises(ProtectedError):
        series.delete()
    with pytest.raises(ProtectedError):
        source.delete()
    revision.delete()
    assert not RevisionWeekday.objects.exists()
    OccurrenceException.objects.create(
        series=series, original_start_date=series.starts_on, kind="cancel"
    )
    with pytest.raises(ProtectedError):
        series.delete()


@pytest.mark.django_db(transaction=True)
def test_concurrent_overlapping_revision_inserts_cannot_both_commit(series):
    barrier = Barrier(2)
    series_id = series.pk

    def insert_revision():
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '5s'")
                    cursor.execute("SET LOCAL statement_timeout = '10s'")
                barrier.wait(timeout=10)
                values = revision_values(None)
                values.pop("series")
                SeriesRevision.objects.create(**values, series_id=series_id)
            return "committed"
        except IntegrityError as error:
            assert error.__cause__.diag.constraint_name == "series_revision_periods_do_not_overlap"
            return "excluded"
        except OperationalError as error:
            # Raw concurrent GiST inserts can wait on each other's tentative
            # entries. PostgreSQL may abort one as a deadlock victim instead of
            # raising an exclusion violation. Either way only one may commit.
            # Service concurrency tests require both writes to complete under
            # the parent lock; do not catch/retry deadlocks in those tests.
            assert error.__cause__.sqlstate == "40P01"
            return "excluded"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: insert_revision(), range(2)))
    assert sorted(outcomes) == ["committed", "excluded"]
    assert SeriesRevision.objects.filter(series=series).count() == 1


def test_invalid_exception_foreign_keys_report_validation_errors(series, halifax_time):
    replacement = OccurrenceException(
        series=series, original_start_date=series.starts_on, kind="reschedule",
        replacement_source_id=99999999, replacement_title="Moved class",
        starts_at=halifax_time("2026-11-02T09:00"),
        ends_at=halifax_time("2026-11-02T11:00"),
    )
    with pytest.raises(ValidationError) as error:
        replacement.full_clean()
    assert "replacement_source" in error.value.message_dict
