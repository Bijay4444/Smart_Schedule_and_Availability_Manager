"""Small UTC interval operations shared by scheduling calculations."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from .time_resolution import resolve_local_time


@dataclass(frozen=True, order=True)
class Interval:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self):
        for value in (self.starts_at, self.ends_at):
            if not isinstance(value, datetime) or timezone.is_naive(value):
                raise ValidationError("Interval endpoints must be aware datetimes.")
        object.__setattr__(self, "starts_at", self.starts_at.astimezone(UTC))
        object.__setattr__(self, "ends_at", self.ends_at.astimezone(UTC))
        if self.ends_at <= self.starts_at:
            raise ValidationError("An interval must have a positive elapsed duration.")


def query_interval(starts_at, ends_at):
    interval = Interval(starts_at, ends_at)
    if interval.ends_at - interval.starts_at > timedelta(days=366):
        raise ValidationError("Query at most 366 elapsed days.")
    if (
        interval.starts_at.date() <= date.min + timedelta(days=3)
        or interval.ends_at.date() >= date.max - timedelta(days=3)
    ):
        raise ValidationError("Query dates are too close to the calendar limits.")
    return interval


def date_bounds(day, time_zone):
    """Resolve both midnights independently; local dates may have 23 or 25 hours."""
    return tuple(resolve_local_time(datetime.combine(value, time.min), time_zone).value.astimezone(UTC)
                 for value in (day, day + timedelta(days=1)))


def resolution_affected_dates(start, end):
    """Include requested and resolved dates when automatic clocks need review."""
    days = (start.requested.date(), end.requested.date(), start.value.date(), end.value.date())
    zone = start.value.tzinfo.key
    lower, _ = date_bounds(min(days), zone)
    _, upper = date_bounds(max(days), zone)
    return Interval(lower, upper)


def merge_intervals(intervals):
    merged = []
    for item in sorted(intervals):
        if merged and item.starts_at <= merged[-1].ends_at:
            merged[-1] = Interval(merged[-1].starts_at, max(merged[-1].ends_at, item.ends_at))
        else:
            merged.append(item)
    return tuple(merged)


def clip_intervals(intervals, bounds):
    return tuple(Interval(max(item.starts_at, bounds.starts_at), min(item.ends_at, bounds.ends_at))
                 for item in intervals
                 if item.starts_at < bounds.ends_at and item.ends_at > bounds.starts_at)


def subtract_intervals(windows, occupied):
    """Subtract a union of occupied intervals; touching endpoints leave no overlap."""
    occupied = merge_intervals(occupied)
    result = []
    for window in merge_intervals(windows):
        cursor = window.starts_at
        for item in occupied:
            if item.ends_at <= cursor:
                continue
            if item.starts_at >= window.ends_at:
                break
            if item.starts_at > cursor:
                result.append(Interval(cursor, item.starts_at))
            cursor = max(cursor, item.ends_at)
            if cursor >= window.ends_at:
                break
        if cursor < window.ends_at:
            result.append(Interval(cursor, window.ends_at))
    return tuple(result)
