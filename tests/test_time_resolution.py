from datetime import UTC, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError

from scheduling.time_resolution import resolve_local_time


def test_normal_time_keeps_local_clock_without_adjustment():
    resolved = resolve_local_time(datetime(2026, 10, 26, 9), "America/Halifax")
    assert resolved.value.astimezone(UTC) == datetime(2026, 10, 26, 12, tzinfo=UTC)
    assert resolved.requested == datetime(2026, 10, 26, 9)
    assert resolved.adjustment is None


def test_missing_halifax_time_moves_by_gap_preserving_minutes():
    resolved = resolve_local_time(datetime(2026, 3, 8, 2, 30), "America/Halifax")
    assert resolved.value.replace(tzinfo=None) == datetime(2026, 3, 8, 3, 30)
    assert resolved.value.astimezone(UTC) == datetime(2026, 3, 8, 6, 30, tzinfo=UTC)
    assert resolved.adjustment == "gap_shift_forward"


def test_repeated_time_chooses_first_even_if_input_has_fold_one():
    resolved = resolve_local_time(datetime(2026, 11, 1, 1, 30, fold=1), "America/Halifax")
    assert resolved.value.fold == 0
    assert resolved.value.utcoffset() == -timedelta(hours=3)
    assert resolved.value.astimezone(UTC) == datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
    assert resolved.adjustment == "fold_first"


def test_gap_is_not_assumed_to_be_an_hour():
    resolved = resolve_local_time(datetime(2026, 10, 4, 2, 15), "Australia/Lord_Howe")
    assert resolved.value.replace(tzinfo=None) == datetime(2026, 10, 4, 2, 45)
    assert resolved.adjustment == "gap_shift_forward"


def test_skipped_calendar_date_moves_forward_by_full_date_change():
    resolved = resolve_local_time(datetime(2011, 12, 30, 9), "Pacific/Apia")
    assert resolved.value.replace(tzinfo=None) == datetime(2011, 12, 31, 9)
    assert resolved.adjustment == "gap_shift_forward"


@pytest.mark.parametrize("value,zone,policies", [
    (datetime(2026, 10, 26, 9, tzinfo=UTC), "America/Halifax", {}),
    (datetime(2026, 10, 26, 9), "Not/AZone", {}),
    (datetime(2026, 10, 26, 9), "America/Halifax", {"gap_policy": "skip"}),
    (datetime(2026, 10, 26, 9), "America/Halifax", {"fold_policy": "second"}),
])
def test_invalid_local_inputs_or_unsupported_policies_are_rejected(value, zone, policies):
    with pytest.raises(ValidationError):
        resolve_local_time(value, zone, **policies)
