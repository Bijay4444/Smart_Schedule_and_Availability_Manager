"""Review recurring writes against a staged schedule before committing them.

The lower-level recurrence services retain their integrity-focused interfaces.
Browser writes enter here and require a signed review of the current result.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from .conflicts import recurring_for_intervals
from .intervals import Interval, date_bounds, resolution_affected_dates
from .models import Commitment, RecurringSeries
from .recurrence import (
    Occurrence, OccurrenceIssue, _exception_target, create_series, reschedule_occurrence, revise_series,
)


@dataclass(frozen=True)
class RecurringConflict:
    candidate: Occurrence
    other: Commitment | Occurrence


@dataclass(frozen=True)
class RecurringReview:
    starts_on: date
    through: date
    limited: bool
    occurrences: tuple[Occurrence, ...]
    conflicts: tuple[RecurringConflict, ...]
    issues: tuple[OccurrenceIssue, ...]

    @property
    def adjustments(self):
        return tuple(item for item in self.occurrences
                     if any(endpoint and endpoint.adjustment
                            for endpoint in (item.start_resolution, item.end_resolution)))

    @property
    def conflict_groups(self):
        groups = {}
        for pair in self.conflicts:
            key = ("one_time", pair.other.pk) if isinstance(pair.other, Commitment) else ("series", pair.other.series_id)
            groups.setdefault(key, []).append(pair)
        return tuple({"title": pairs[0].other.title, "count": len(pairs),
                      "first": pairs[0], "remaining": tuple(pairs[1:])} for pairs in groups.values())


class ReviewRequired(Exception):
    def __init__(self, preview, token, changed=False):
        self.preview = preview
        self.token = token
        self.changed = changed
        super().__init__("Review the current recurring schedule before saving.")


def owned_series(*, owner, series_id):
    series = RecurringSeries.objects.filter(pk=series_id, source__owner=owner).select_related("source").first()
    if series is None:
        raise PermissionDenied
    return series


def edit_initial(*, owner, series_id, effective_from):
    series = owned_series(owner=owner, series_id=series_id)
    revision = series.revisions.filter(effective_from__lte=effective_from).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=effective_from)
    ).first()
    if revision is None:
        revision = series.revisions.order_by("effective_from").first()
    return {
        "effective_from": effective_from, "title": revision.title,
        "start_time": revision.start_time, "end_time": revision.end_time,
        "ends_next_day": bool(revision.end_day_offset),
        "weekdays": list(revision.weekdays.values_list("weekday", flat=True)),
    }


def occurrence_initial(*, owner, series_id, original_date):
    series = owned_series(owner=owner, series_id=series_id)
    exception = _exception_target(series, original_date)
    zone = ZoneInfo(series.time_zone)
    if exception.kind == "reschedule":
        start, end = exception.starts_at.astimezone(zone), exception.ends_at.astimezone(zone)
        title, source_id = exception.replacement_title, exception.replacement_source_id
    else:
        values = edit_initial(owner=owner, series_id=series_id, effective_from=original_date)
        from .time_resolution import resolve_local_time
        start = resolve_local_time(datetime.combine(original_date, values["start_time"]), series.time_zone).value
        end_day = original_date + timedelta(days=int(values["ends_next_day"]))
        end = resolve_local_time(datetime.combine(end_day, values["end_time"]), series.time_zone).value
        title, source_id = values["title"], series.source_id
    return {
        "replacement_title": title, "replacement_source": source_id,
        "starts_at": start.strftime("%Y-%m-%dT%H:%M"), "ends_at": end.strftime("%Y-%m-%dT%H:%M"),
        "second_start": bool(start.fold), "second_end": bool(end.fold),
    }


def _identity(item, own_series):
    if isinstance(item, Commitment):
        return ("one_time", item.pk)
    return ("series", "own" if item.series_id == own_series else item.series_id,
            item.original_start_date.isoformat())


def _summary(item, own_series):
    return (_identity(item, own_series), item.title, item.source.pk, item.source.name,
            item.starts_at.astimezone(UTC).isoformat(), item.ends_at.astimezone(UTC).isoformat())


def _overlaps(left, right):
    return left.starts_at < right.ends_at and left.ends_at > right.starts_at


def _review(*, owner, series, first, through, limited, candidates=None):
    start, _ = date_bounds(first, series.time_zone)
    end, _ = date_bounds(through + timedelta(days=2), series.time_zone)
    initial = recurring_for_intervals(owner=owner, intervals=[Interval(start, end)])
    if candidates is None:
        last_midnight, _ = date_bounds(through + timedelta(days=1), series.time_zone)
        candidates = tuple(item for item in initial.occurrences if item.series_id == series.pk and (
            first <= item.original_start_date <= through if not item.is_replacement
            else item.starts_at < last_midnight and item.ends_at > start
        ))
    own_issues = tuple(issue for issue in initial.issues
                       if issue.series_id == series.pk and first <= issue.original_start_date <= through)
    intervals = [Interval(item.starts_at, item.ends_at) for item in candidates]
    intervals.extend(resolution_affected_dates(issue.start_resolution, issue.end_resolution) for issue in own_issues)
    recurring = recurring_for_intervals(owner=owner, intervals=intervals)
    one_time = []
    if intervals:
        one_time = list(Commitment.objects.filter(
            source__owner=owner, starts_at__lt=max(item.ends_at for item in intervals),
            ends_at__gt=min(item.starts_at for item in intervals),
        ).select_related("source"))
    candidate_keys = {item.key for item in candidates}
    conflicts, active, seen = [], [], set()
    for item in sorted([*one_time, *recurring.occurrences], key=lambda item: (item.starts_at, item.ends_at)):
        active = [previous for previous in active if previous.ends_at > item.starts_at]
        for previous in active:
            own = isinstance(item, Occurrence) and item.key in candidate_keys
            previous_own = isinstance(previous, Occurrence) and previous.key in candidate_keys
            if not (own or previous_own):
                continue
            pair = frozenset((_identity(item, series.pk), _identity(previous, series.pk)))
            if pair not in seen:
                seen.add(pair)
                conflicts.append(RecurringConflict(item, previous) if own else RecurringConflict(previous, item))
        active.append(item)
    issues = {(item.series_id, item.original_start_date): item for item in own_issues}
    for issue in recurring.issues:
        affected = resolution_affected_dates(issue.start_resolution, issue.end_resolution)
        if any(_overlaps(affected, item) for item in intervals):
            issues[issue.series_id, issue.original_start_date] = issue
    return RecurringReview(first, through, limited, tuple(candidates), tuple(conflicts),
                           tuple(sorted(issues.values(), key=lambda item: (item.original_start_date, item.series_id))))


def _confirm(*, owner, series, action, values, preview, token, confirmed):
    # The transient ID of a staged new series changes after rollback, so normalize
    # its identity. Every existing counterpart retains its stable identity.
    payload = {
        "owner": owner.pk, "action": action, "values": values,
        "range": (preview.starts_on, preview.through, preview.limited),
        "occurrences": [_summary(item, series.pk) for item in preview.occurrences],
        "conflicts": [(_summary(pair.candidate, series.pk), _summary(pair.other, series.pk))
                      for pair in preview.conflicts],
        "issues": [("own" if item.series_id == series.pk else item.series_id,
                    item.original_start_date, item.title, item.start_resolution, item.end_resolution)
                   for item in preview.issues],
        "adjustments": [(item.original_start_date, item.start_resolution, item.end_resolution)
                        for item in preview.adjustments],
    }
    digest = hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()
    matched = False
    if token:
        try:
            matched = signing.loads(token, salt="recurring-review", max_age=3600) == digest
        except signing.BadSignature:
            pass
    if not (confirmed and matched):
        raise ReviewRequired(preview, signing.dumps(digest, salt="recurring-review"), bool(token))


def _preview_dates(series, first):
    if not isinstance(first, date) or isinstance(first, datetime) or not 1 < first.year < 9998:
        raise ValidationError("Choose a date between years 0002 and 9997.")
    try:
        next_year = first.replace(year=first.year + 1)
    except ValueError:  # February 29 becomes February 28 in the next year.
        next_year = first.replace(year=first.year + 1, day=28)
    end = min(next_year, series.ends_before or next_year)
    if end <= first:
        raise ValidationError("The series has no remaining dates to edit.")
    return end - timedelta(days=1), series.ends_before is None or series.ends_before > end


@transaction.atomic
def save_recurring_series(*, owner, values, series_id=None, review_token=None, confirmed=False):
    """Stage, inspect the next twelve months, then save only a matching review.

    Raising ReviewRequired rolls the entire staged create/revision back. A final
    submission repeats the write and read under the common owner lock.
    """
    values = dict(values)
    if series_id is None:
        series = create_series(owner=owner, **values)
        first = series.starts_on
    else:
        revise_series(owner=owner, series_id=series_id, **values)
        series = owned_series(owner=owner, series_id=series_id)
        first = values["effective_from"]
    through, limited = _preview_dates(series, first)
    preview = _review(owner=owner, series=series, first=first, through=through, limited=limited)
    _confirm(owner=owner, series=series, action=("revise", series_id) if series_id else "create",
             values=values, preview=preview, token=review_token, confirmed=confirmed)
    return series


@transaction.atomic
def save_occurrence_change(*, owner, values, review_token=None, confirmed=False):
    """Review the entire finite replacement, excluding only its original occurrence."""
    exception = reschedule_occurrence(owner=owner, **values)
    series = owned_series(owner=owner, series_id=exception.series_id)
    result = recurring_for_intervals(owner=owner, intervals=[Interval(exception.starts_at, exception.ends_at)])
    candidates = tuple(item for item in result.occurrences if item.key == (series.pk, exception.original_start_date))
    zone = ZoneInfo(series.time_zone)
    first = exception.starts_at.astimezone(zone).date()
    through = (exception.ends_at - timedelta(microseconds=1)).astimezone(zone).date()
    preview = _review(owner=owner, series=series, first=first, through=through, limited=False, candidates=candidates)
    _confirm(owner=owner, series=series, action="reschedule", values=values,
             preview=preview, token=review_token, confirmed=confirmed)
    return exception
