"""Private recurring schedule services; browser/API integration follows separately.

Writes preserve earlier dates and explicit exceptions. Conflict preflight is a
separate integration step before recurring writes are exposed to users.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.utils import timezone

from .models import (
    CommitmentSource, OccurrenceException, RecurringSeries, RevisionWeekday, SeriesRevision,
)
from .time_resolution import ResolvedTime, resolve_local_time


@dataclass(frozen=True)
class Occurrence:
    series_id: int
    original_start_date: date
    source: CommitmentSource
    title: str
    starts_at: datetime  # UTC; rendering may use a different zone.
    ends_at: datetime
    start_resolution: ResolvedTime | None = None
    end_resolution: ResolvedTime | None = None
    is_replacement: bool = False

    @property
    def key(self):
        return self.series_id, self.original_start_date


@dataclass(frozen=True)
class OccurrenceIssue:
    series_id: int
    original_start_date: date
    title: str
    start_resolution: ResolvedTime
    end_resolution: ResolvedTime
    message: str = "Automatic clock resolution leaves no positive interval; review this date."


@dataclass(frozen=True)
class OccurrenceResult:
    occurrences: tuple[Occurrence, ...]
    issues: tuple[OccurrenceIssue, ...]

    @property
    def complete(self):
        return not self.issues


def _require_date(value, field):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValidationError({field: "Provide a calendar date."})
    return value


def _selected_weekdays(values):
    try:
        values = tuple(values)
    except TypeError:
        raise ValidationError({"weekdays": "Choose at least one weekday."})
    if (
        not values or any(type(value) is not int or not 0 <= value <= 6 for value in values)
        or len(set(values)) != len(values)
    ):
        raise ValidationError({"weekdays": "Choose distinct weekdays from Monday (0) to Sunday (6)."})
    return sorted(values)


def _local_clocks(start_time, end_time):
    errors = {}
    for field, value in (("start_time", start_time), ("end_time", end_time)):
        if not isinstance(value, time) or value.tzinfo is not None:
            errors[field] = "Provide a local clock time without a UTC offset."
    if errors:
        raise ValidationError(errors)


def _owned_series(*, owner, series_id, lock=False):
    query = RecurringSeries.objects.filter(pk=series_id, source__owner=owner)
    if lock:
        # Lock only the stable series, not joined source rows. All series edits
        # and exceptions acquire this same lock, even when no children exist.
        query = query.select_for_update(of=("self",))
    series = query.select_related("source").first()
    if series is None:
        raise PermissionDenied
    return series


def _owned_source(*, owner, source_id):
    source = CommitmentSource.objects.select_for_update().filter(
        pk=source_id, owner=owner
    ).first()
    if source is None:
        raise PermissionDenied
    return source


def _save_revision(revision, weekdays):
    revision.full_clean()
    revision.save()
    RevisionWeekday.objects.bulk_create(
        [RevisionWeekday(revision=revision, weekday=day) for day in weekdays]
    )
    return revision


@transaction.atomic
def create_series(
    *, owner, source_id, title, starts_on, start_time, end_time, weekdays,
    end_day_offset=0, ends_on=None, time_zone="America/Halifax",
):
    """Create a complete rule atomically; ends_on is the inclusive last start date."""
    source = _owned_source(owner=owner, source_id=source_id)
    if source.archived_at:
        raise ValidationError({"source": "Choose an active source for a new series."})
    _require_date(starts_on, "starts_on")
    _local_clocks(start_time, end_time)
    weekdays = _selected_weekdays(weekdays)
    ends_before = None
    if ends_on is not None:
        _require_date(ends_on, "ends_on")
        if ends_on < starts_on or ends_on == date.max:
            raise ValidationError({"ends_on": "Choose a final date on or after the start and before 9999-12-31."})
        ends_before = ends_on + timedelta(days=1)
    series = RecurringSeries(
        source=source, time_zone=time_zone, starts_on=starts_on, ends_before=ends_before
    )
    series.full_clean()
    series.save()
    _save_revision(SeriesRevision(
        series=series, effective_from=starts_on, title=title,
        start_time=start_time, end_time=end_time, end_day_offset=end_day_offset,
    ), weekdays)
    return series


def _future_date(series, value, field):
    _require_date(value, field)
    today = timezone.now().astimezone(ZoneInfo(series.time_zone)).date()
    if value < today:
        raise ValidationError({field: "Choose today or a future date to preserve earlier schedules."})


@transaction.atomic
def revise_series(
    *, owner, series_id, effective_from, title, start_time, end_time,
    weekdays, end_day_offset=0,
):
    """Replace the regular pattern from this date, including later planned rules.

    Earlier portions and every explicit exception retain their identity/content.
    The series' original source, zone, and lifetime are unchanged.
    """
    series = _owned_series(owner=owner, series_id=series_id, lock=True)
    _future_date(series, effective_from, "effective_from")
    if effective_from < series.starts_on or (
        series.ends_before is not None and effective_from >= series.ends_before
    ):
        raise ValidationError({"effective_from": "Choose a date within the series lifetime."})
    weekdays = _selected_weekdays(weekdays)
    previous = series.revisions.filter(effective_from__lte=effective_from).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=effective_from)
    ).first()
    if previous is None:
        raise ValidationError("The series has no regular rule on that date; review its revisions.")
    _local_clocks(start_time, end_time)

    successor = SeriesRevision(
        series=series, effective_from=effective_from, title=title,
        start_time=start_time, end_time=end_time, end_day_offset=end_day_offset,
        dst_gap_policy=previous.dst_gap_policy, dst_fold_policy=previous.dst_fold_policy,
    )
    # Validate fields before touching existing rows; exclusion validation follows
    # after the old range is closed, inside the same transaction.
    successor.full_clean(validate_constraints=False)
    series.revisions.filter(effective_from__gte=effective_from).delete()
    if previous.effective_from < effective_from:
        previous.effective_until = effective_from
        previous.save(update_fields=["effective_until"])
    return _save_revision(successor, weekdays)


@transaction.atomic
def end_series(*, owner, series_id, ends_before):
    """Shorten a series by original start date; never extend/reopen it."""
    series = _owned_series(owner=owner, series_id=series_id, lock=True)
    _future_date(series, ends_before, "ends_before")
    cutoff = max(ends_before, series.starts_on)
    if series.ends_before is not None:
        cutoff = min(cutoff, series.ends_before)
    series.ends_before = cutoff
    series.full_clean()
    series.save(update_fields=["ends_before"])
    return series


def _exception_target(series, original_start_date):
    _require_date(original_start_date, "original_start_date")
    if original_start_date < series.starts_on or (
        series.ends_before is not None and original_start_date >= series.ends_before
    ):
        raise ValidationError({"original_start_date": "Choose an occurrence inside the series lifetime."})
    existing = series.exceptions.filter(original_start_date=original_start_date).first()
    if existing is not None:
        return existing  # A later weekday change must not invalidate an exception.
    has_occurrence = series.revisions.filter(
        effective_from__lte=original_start_date,
        weekdays__weekday=original_start_date.weekday(),
    ).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=original_start_date)
    ).exists()
    if not has_occurrence:
        raise ValidationError({"original_start_date": "No occurrence is scheduled on that original date."})
    return OccurrenceException(series=series, original_start_date=original_start_date)


@transaction.atomic
def cancel_occurrence(*, owner, series_id, original_start_date):
    series = _owned_series(owner=owner, series_id=series_id, lock=True)
    exception = _exception_target(series, original_start_date)
    exception.kind = OccurrenceException.Kind.CANCEL
    exception.replacement_source = None
    exception.replacement_title = None
    exception.starts_at = None
    exception.ends_at = None
    exception.full_clean()
    exception.save()
    return exception


@transaction.atomic
def reschedule_occurrence(
    *, owner, series_id, original_start_date, replacement_source_id,
    replacement_title, starts_at, ends_at,
):
    """Store explicit aware instants, including a user's choice of the second fold."""
    # Source first, series second: match source assignment lock order.
    source = _owned_source(owner=owner, source_id=replacement_source_id)
    series = _owned_series(owner=owner, series_id=series_id, lock=True)
    exception = _exception_target(series, original_start_date)
    if source.archived_at and source.pk not in (series.source_id, exception.replacement_source_id):
        raise ValidationError({"replacement_source": "Choose an active source for a new assignment."})
    errors = {}
    for field, value in (("starts_at", starts_at), ("ends_at", ends_at)):
        if not isinstance(value, datetime) or timezone.is_naive(value):
            errors[field] = "Provide a datetime with a time zone."
    if errors:
        raise ValidationError(errors)
    exception.kind = OccurrenceException.Kind.RESCHEDULE
    exception.replacement_source = source
    exception.replacement_title = replacement_title
    exception.starts_at = starts_at
    exception.ends_at = ends_at
    exception.full_clean()
    exception.save()
    return exception


def _query_bounds(starts_at, ends_at):
    for value in (starts_at, ends_at):
        if not isinstance(value, datetime) or timezone.is_naive(value):
            raise ValidationError("Query endpoints must be aware datetimes.")
    start, end = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
    if end <= start or end - start > timedelta(days=366):
        raise ValidationError("Query a positive interval of at most 366 elapsed days.")
    # Timezone offsets, next-day ends, and skipped dates need a small nominal-date
    # margin. UTC offsets are <24h; IANA's largest forward date jump is 24h.
    if start.date() <= date.min + timedelta(days=3) or end.date() >= date.max - timedelta(days=3):
        raise ValidationError("Query dates are too close to the calendar limits.")
    return start, end


def _active_original_date():
    return Q(original_start_date__gte=F("series__starts_on")) & (
        Q(series__ends_before__isnull=True)
        | Q(original_start_date__lt=F("series__ends_before"))
    )


def occurrences_for_user(*, owner, starts_at, ends_at):
    """Return whole occurrences overlapping [start, end), plus review issues.

    The caller clips intervals for weekly rendering. No generated rows are saved.
    Issues mark affected local dates incomplete, including overnight carry-in.
    """
    start, end = _query_bounds(starts_at, ends_at)
    first_date = start.date() - timedelta(days=3)
    until_date = end.date() + timedelta(days=3)
    revision_query = SeriesRevision.objects.filter(effective_from__lt=until_date).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=first_date)
    ).prefetch_related("weekdays")
    series_list = list(RecurringSeries.objects.filter(
        source__owner=owner, starts_on__lt=until_date
    ).filter(
        Q(ends_before__isnull=True) | Q(ends_before__gt=first_date)
    ).select_related("source").prefetch_related(Prefetch("revisions", queryset=revision_query)))
    exceptions = set(OccurrenceException.objects.filter(
        series__in=series_list, original_start_date__gte=first_date,
        original_start_date__lt=until_date,
    ).values_list("series_id", "original_start_date"))
    occurrences, issues = [], []
    for series in series_list:
        zone = ZoneInfo(series.time_zone)
        local_first = start.astimezone(zone).date()
        local_last = (end - timedelta(microseconds=1)).astimezone(zone).date()
        for revision in series.revisions.all():
            lower = max(first_date, series.starts_on, revision.effective_from)
            upper = min(until_date, series.ends_before or until_date, revision.effective_until or until_date)
            for weekday in revision.weekdays.all():
                first_ordinal = lower.toordinal() + (weekday.weekday - lower.weekday()) % 7
                for ordinal in range(first_ordinal, upper.toordinal(), 7):
                    day = date.fromordinal(ordinal)
                    if (series.pk, day) not in exceptions:
                        resolved_start = resolve_local_time(
                            datetime.combine(day, revision.start_time), series.time_zone,
                            gap_policy=revision.dst_gap_policy, fold_policy=revision.dst_fold_policy,
                        )
                        resolved_end = resolve_local_time(
                            datetime.combine(day + timedelta(days=revision.end_day_offset), revision.end_time),
                            series.time_zone, gap_policy=revision.dst_gap_policy,
                            fold_policy=revision.dst_fold_policy,
                        )
                        actual_start = resolved_start.value.astimezone(UTC)
                        actual_end = resolved_end.value.astimezone(UTC)
                        if actual_end <= actual_start:
                            affected_first = min(day, resolved_start.value.date(), resolved_end.value.date())
                            affected_last = max(
                                day + timedelta(days=revision.end_day_offset),
                                resolved_start.value.date(), resolved_end.value.date(),
                            )
                            if affected_first <= local_last and affected_last >= local_first:
                                issues.append(OccurrenceIssue(
                                    series.pk, day, revision.title, resolved_start, resolved_end
                                ))
                        elif actual_start < end and actual_end > start:
                            occurrences.append(Occurrence(
                                series.pk, day, series.source, revision.title,
                                actual_start, actual_end, resolved_start, resolved_end,
                            ))

    # Query actual replacement intervals independently: their original dates or
    # their parent's entire nominal lifetime may be far outside this query.
    replacements = OccurrenceException.objects.filter(
        _active_original_date(), series__source__owner=owner,
        replacement_source__owner=owner, kind=OccurrenceException.Kind.RESCHEDULE,
        starts_at__lt=end, ends_at__gt=start,
    ).select_related("replacement_source")
    for replacement in replacements:
        occurrences.append(Occurrence(
            replacement.series_id, replacement.original_start_date,
            replacement.replacement_source, replacement.replacement_title,
            replacement.starts_at.astimezone(UTC), replacement.ends_at.astimezone(UTC),
            is_replacement=True,
        ))
    return OccurrenceResult(
        tuple(sorted(occurrences, key=lambda item: (item.starts_at, item.series_id, item.original_start_date))),
        tuple(sorted(issues, key=lambda item: (item.original_start_date, item.series_id))),
    )
