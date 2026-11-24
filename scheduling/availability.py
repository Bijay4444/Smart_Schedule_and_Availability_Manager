"""Calculate willingness minus commitments and inspect unsaved proposed shifts."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError

from .intervals import (
    Interval, clip_intervals, date_bounds, merge_intervals, query_interval,
    resolution_affected_dates, subtract_intervals,
)
from .models import Commitment
from .recurrence import Occurrence, OccurrenceIssue, occurrences_for_user
from .working_windows import (
    WORKING_ZONE, WorkingIssue, WorkingResolution, working_windows_for_user,
)


@dataclass(frozen=True)
class AvailabilityResult:
    working_windows: tuple[Interval, ...]
    available: tuple[Interval, ...]
    commitments: tuple[Commitment | Occurrence, ...]
    working_issues: tuple[WorkingIssue, ...]
    commitment_issues: tuple[OccurrenceIssue, ...]
    adjustments: tuple[WorkingResolution, ...]
    withheld: tuple[Interval, ...]

    @property
    def complete(self):
        return not (self.working_issues or self.commitment_issues)


@dataclass(frozen=True)
class AvailabilityDay:
    local_date: date
    intervals: tuple[Interval, ...]
    complete: bool


@dataclass(frozen=True)
class WeeklyAvailability:
    starts_on: date
    days: tuple[AvailabilityDay, ...]
    result: AvailabilityResult

    @property
    def complete(self):
        return self.result.complete


@dataclass(frozen=True)
class ShiftCheck:
    conflicts: tuple[Commitment | Occurrence, ...]
    outside_working_windows: tuple[Interval, ...]
    availability: AvailabilityResult

    @property
    def complete(self):
        return self.availability.complete

    @property
    def is_available(self):
        return self.complete and not self.conflicts and not self.outside_working_windows


def availability_for_user(*, owner, starts_at, ends_at):
    """Return bounded UTC intervals; incomplete dates never offer availability."""
    bounds = query_interval(starts_at, ends_at)
    working = working_windows_for_user(owner=owner, starts_at=bounds.starts_at, ends_at=bounds.ends_at)
    recurring = occurrences_for_user(owner=owner, starts_at=bounds.starts_at, ends_at=bounds.ends_at)
    one_time = list(Commitment.objects.filter(
        source__owner=owner, starts_at__lt=bounds.ends_at, ends_at__gt=bounds.starts_at,
    ).select_related("source"))
    commitments = tuple(sorted(
        [*one_time, *recurring.occurrences], key=lambda item: (item.starts_at, item.ends_at),
    ))
    withheld = [issue.affected for issue in working.issues]
    for issue in recurring.issues:
        withheld.extend(clip_intervals([
            resolution_affected_dates(issue.start_resolution, issue.end_resolution)
        ], bounds))
    withheld = merge_intervals(withheld)
    occupied = [Interval(item.starts_at, item.ends_at) for item in commitments]
    return AvailabilityResult(
        working.intervals, subtract_intervals(working.intervals, [*occupied, *withheld]),
        commitments, working.issues, recurring.issues, working.adjustments, withheld,
    )


def weekly_availability_for_user(*, owner, anchor):
    """Group a Monday–Sunday Halifax week into local dates for future presentation."""
    if not isinstance(anchor, date) or isinstance(anchor, datetime) or not 1 < anchor.year < 9999:
        raise ValidationError("Provide a calendar date between years 0002 and 9998.")
    monday = anchor - timedelta(days=anchor.weekday())
    start, _ = date_bounds(monday, WORKING_ZONE)
    end, _ = date_bounds(monday + timedelta(days=7), WORKING_ZONE)
    result = availability_for_user(owner=owner, starts_at=start, ends_at=end)
    days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        lower, upper = date_bounds(day, WORKING_ZONE)
        bounds = Interval(lower, upper)
        days.append(AvailabilityDay(
            day, clip_intervals(result.available, bounds),
            not clip_intervals(result.withheld, bounds),
        ))
    return WeeklyAvailability(monday, tuple(days), result)


def check_proposed_shift(*, owner, starts_at, ends_at):
    """Read only: distinguish commitment overlaps, outside hours, and review issues."""
    bounds = query_interval(starts_at, ends_at)
    result = availability_for_user(owner=owner, starts_at=bounds.starts_at, ends_at=bounds.ends_at)
    return ShiftCheck(
        result.commitments, subtract_intervals([bounds], result.working_windows), result,
    )
