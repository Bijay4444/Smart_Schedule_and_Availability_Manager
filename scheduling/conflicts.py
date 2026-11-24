"""Conflict inspection for finite commitment intervals, without working-window rules."""

from dataclasses import dataclass
from datetime import date, timedelta

from .intervals import Interval, merge_intervals, resolution_affected_dates
from .models import Commitment
from .recurrence import Occurrence, OccurrenceIssue, OccurrenceResult, occurrences_for_user


@dataclass(frozen=True)
class ConflictCheck:
    conflicts: tuple[Commitment | Occurrence, ...]
    issues: tuple[OccurrenceIssue, ...]

    @property
    def complete(self):
        return not self.issues


def find_conflicts(*, owner, starts_at, ends_at, exclude_pk=None):
    """Low-level one-time queryset, also usable with SQL expressions.

    Use inspect_conflicts for the combined one-time/recurring warning result.
    Strict inequalities allow one commitment to start as another ends.
    """
    conflicts = Commitment.objects.filter(
        source__owner=owner, starts_at__lt=ends_at, ends_at__gt=starts_at,
    ).select_related("source")
    if exclude_pk is not None:
        conflicts = conflicts.exclude(pk=exclude_pk)
    return conflicts


def _query_periods(intervals):
    """Batch nearby intervals and split long ones into supported recurrence queries.

    Never expand an arbitrary gap between distant commitments. Existing one-time
    commitments may last more than a year, so check every chunk of their duration.
    """
    pending = None
    for interval in merge_intervals(intervals):
        cursor = interval.starts_at
        while cursor < interval.ends_at:
            end = cursor + min(timedelta(days=366), interval.ends_at - cursor)
            if pending and end - pending.starts_at <= timedelta(days=366):
                pending = Interval(pending.starts_at, end)
            else:
                if pending:
                    yield pending
                pending = Interval(cursor, end)
            cursor = end
    if pending:
        yield pending


def recurring_for_intervals(*, owner, intervals):
    """Expand finite intervals in supported chunks and deduplicate identities."""
    occurrences, issues = {}, {}
    for bounds in _query_periods(intervals):
        result = occurrences_for_user(owner=owner, starts_at=bounds.starts_at, ends_at=bounds.ends_at)
        for item in result.occurrences:
            occurrences[item.key] = item
        for issue in result.issues:
            issues[issue.series_id, issue.original_start_date] = issue
    return OccurrenceResult(
        tuple(sorted(occurrences.values(), key=lambda item: (item.starts_at, item.key))),
        tuple(sorted(issues.values(), key=lambda item: (item.original_start_date, item.series_id))),
    )


def _overlaps(left, right):
    return left.starts_at < right.ends_at and left.ends_at > right.starts_at


def inspect_conflicts(*, owner, starts_at, ends_at, exclude_pk=None):
    """Return all overlapping commitments plus dates whose check needs review.

    exclude_pk applies only to a one-time commitment; recurring identities are
    separate and may have the same numeric ID. No writes or window checks occur.
    """
    bounds = Interval(starts_at, ends_at)
    recurring = recurring_for_intervals(owner=owner, intervals=[bounds])
    one_time = list(find_conflicts(
        owner=owner, starts_at=bounds.starts_at, ends_at=bounds.ends_at, exclude_pk=exclude_pk,
    ))
    return ConflictCheck(
        tuple(sorted([*one_time, *recurring.occurrences], key=lambda item: (item.starts_at, item.ends_at))),
        tuple(issue for issue in recurring.issues
              if _overlaps(bounds, resolution_affected_dates(issue.start_resolution, issue.end_resolution))),
    )


def mark_recurring_conflicts(*, owner, commitments):
    """Add recurring indicators to the already annotated one-time list in batches."""
    commitments = list(commitments)
    supported = []
    for item in commitments:
        bounds = Interval(item.starts_at, item.ends_at)
        item.conflict_check_complete = (
            bounds.starts_at.date() > date.min + timedelta(days=3)
            and bounds.ends_at.date() < date.max - timedelta(days=3)
        )
        # Legacy rows at extreme calendar limits remain readable even when the
        # recurrence generator cannot safely inspect their dates.
        if item.conflict_check_complete:
            supported.append((item, bounds))
    recurring = recurring_for_intervals(owner=owner, intervals=[bounds for _, bounds in supported])
    affected = [resolution_affected_dates(issue.start_resolution, issue.end_resolution)
                for issue in recurring.issues]
    for item, bounds in supported:
        item.has_conflict |= any(_overlaps(bounds, occurrence) for occurrence in recurring.occurrences)
        item.conflict_check_complete = not any(_overlaps(bounds, interval) for interval in affected)
    return commitments
