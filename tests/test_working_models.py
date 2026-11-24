from datetime import UTC, date, datetime, time

import pytest
from django.db import IntegrityError, transaction

from scheduling.models import (
    OverrideInterval, WorkingDateOverride, WorkingScheduleRevision, WorkingWindow,
)


pytestmark = pytest.mark.django_db


def reject(model, constraint, **values):
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        model.objects.create(**values)
    assert error.value.__cause__.diag.constraint_name == constraint


@pytest.fixture
def revision(owner):
    return WorkingScheduleRevision.objects.create(
        owner=owner, time_zone="America/Halifax", effective_from=date(2026, 10, 26),
    )


def test_revision_exclusion_is_per_person_and_allows_adjacent_periods(revision, owner, other_owner):
    reject(WorkingScheduleRevision, "working_revision_periods_do_not_overlap",
           owner=owner, time_zone="America/Halifax", effective_from=date(2026, 11, 16))
    WorkingScheduleRevision.objects.create(
        owner=other_owner, time_zone="America/Halifax", effective_from=date(2026, 11, 16),
    )
    revision.effective_until = date(2026, 11, 16)
    revision.save()
    WorkingScheduleRevision.objects.create(
        owner=owner, time_zone="America/Halifax", effective_from=date(2026, 11, 16),
    )


@pytest.mark.parametrize("changes,constraint", [
    ({"effective_until": date(2026, 10, 26)}, "working_revision_positive_period"),
    ({"dst_gap_policy": "skip"}, "working_revision_valid_gap_policy"),
    ({"dst_fold_policy": "second"}, "working_revision_valid_fold_policy"),
])
def test_revision_row_checks_without_model_validation(owner, changes, constraint):
    reject(WorkingScheduleRevision, constraint, owner=owner, time_zone="America/Halifax",
           effective_from=date(2026, 10, 26), **changes)


@pytest.mark.parametrize("changes,constraint", [
    ({"weekday": 7}, "working_window_weekday_in_range"),
    ({"end_day_offset": 2}, "working_window_valid_day_offset"),
    ({"end_time": time(8)}, "working_window_positive_local_interval"),
    ({"end_time": time(7)}, "working_window_positive_local_interval"),
])
def test_window_row_checks_without_model_validation(revision, changes, constraint):
    reject(WorkingWindow, constraint, **{
        "revision": revision, "weekday": 0, "start_time": time(8), "end_time": time(12), **changes,
    })


def test_exact_duplicate_windows_rejected_but_overnight_and_overlaps_allowed(revision):
    values = {"revision": revision, "weekday": 0, "start_time": time(22),
              "end_time": time(6), "end_day_offset": 1}
    WorkingWindow.objects.create(**values)
    reject(WorkingWindow, "working_window_unique_rule", **values)
    WorkingWindow.objects.create(**{**values, "start_time": time(23)})


def test_override_unique_date_positive_interval_and_child_cascades(owner):
    values = {"owner": owner, "local_date": date(2026, 10, 26), "time_zone": "America/Halifax"}
    override = WorkingDateOverride.objects.create(**values)
    reject(WorkingDateOverride, "working_override_unique_date", **values)
    reject(OverrideInterval, "working_override_positive_interval", override=override,
           starts_at=datetime(2026, 10, 26, 15, tzinfo=UTC),
           ends_at=datetime(2026, 10, 26, 15, tzinfo=UTC))
    OverrideInterval.objects.create(
        override=override, starts_at=datetime(2026, 10, 26, 15, tzinfo=UTC),
        ends_at=datetime(2026, 10, 26, 16, tzinfo=UTC),
    )
    override.delete()
    assert not OverrideInterval.objects.exists()
