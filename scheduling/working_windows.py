"""Private working-schedule writes and bounded expansion; no commitment subtraction."""

from dataclasses import dataclass
from calendar import day_name
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .intervals import (
    Interval, clip_intervals, date_bounds, merge_intervals, query_interval,
    resolution_affected_dates, subtract_intervals,
)
from .locking import lock_schedule_owner
from .models import OverrideInterval, WorkingDateOverride, WorkingScheduleRevision, WorkingWindow
from .time_resolution import ResolvedTime, resolve_local_time


WORKING_ZONE = "America/Halifax"


@dataclass(frozen=True)
class WindowSpec:
    weekday: int
    start_time: time
    end_time: time
    end_day_offset: int = 0


@dataclass(frozen=True)
class WorkingResolution:
    window_id: int
    original_start_date: date
    start_resolution: ResolvedTime
    end_resolution: ResolvedTime


@dataclass(frozen=True)
class WorkingIssue:
    resolution: WorkingResolution
    affected: Interval
    message: str = "Automatic clock resolution leaves no positive working interval; review this date."


@dataclass(frozen=True)
class WorkingWindowResult:
    intervals: tuple[Interval, ...]
    adjustments: tuple[WorkingResolution, ...]
    issues: tuple[WorkingIssue, ...]

    @property
    def complete(self):
        return not self.issues


@dataclass(frozen=True)
class ResolvedOverride:
    interval: Interval
    notes: tuple[str, ...]


def resolve_override_interval(
    *, local_date, start_time, end_time=None, end_at_midnight=False,
    second_start=False, second_end=False,
):
    """Resolve one same-date clock range, including an explicit next midnight."""
    _require_date(local_date)
    if not isinstance(start_time, time) or start_time.tzinfo is not None:
        raise ValidationError({"start_time": "Enter a local start time."})
    if end_at_midnight:
        if end_time not in (None, time.min):
            raise ValidationError({"end_time": "Clear the end time or use 00:00 for the following midnight."})
        if second_end:
            raise ValidationError({"second_end": "Clear the second-hour choice when ending at midnight."})
        end_local = datetime.combine(local_date + timedelta(days=1), time.min)
    else:
        if not isinstance(end_time, time) or end_time.tzinfo is not None:
            raise ValidationError({"end_time": "Enter an end time or select the following midnight."})
        end_local = datetime.combine(local_date, end_time)
    notes, values = [], []
    for field, local, second in (
        ("start_time", datetime.combine(local_date, start_time), second_start),
        ("end_time", end_local, second_end),
    ):
        resolved = resolve_local_time(local, WORKING_ZONE)
        value = resolved.value
        if second:
            if resolved.adjustment != "fold_first":
                raise ValidationError({"second_start" if field == "start_time" else "second_end":
                                       "This clock time is not repeated. Clear the second-hour option."})
            value = value.replace(fold=1)
            explanation = "second repeated hour"
        else:
            explanation = {"gap_shift_forward": "moved forward for the clock change",
                           "fold_first": "first repeated hour"}.get(resolved.adjustment)
        if explanation:
            notes.append(f"{'Start' if field == 'start_time' else 'End'}: {explanation}, {value:%d %b %Y %H:%M %Z}.")
        values.append(value)
    if values[1].astimezone(UTC) <= values[0].astimezone(UTC):
        raise ValidationError({"end_time": "End must follow start after the clock-change choices."})
    interval = Interval(*values)
    lower, upper = date_bounds(local_date, WORKING_ZONE)
    if interval.starts_at < lower or interval.ends_at > upper:
        raise ValidationError("Keep intervals inside this date; use a separate override for the next date.")
    return ResolvedOverride(interval, tuple(notes))


def working_schedule_initial(*, owner, effective_from):
    """Copy the complete weekly rule active on the chosen date into an editor."""
    return working_schedule_editor_initial(owner=owner, effective_from=effective_from)["windows"]


def working_schedule_editor_initial(*, owner, effective_from):
    """Keep an explicitly empty saved schedule distinct from first-time setup."""
    _require_date(effective_from)
    revision = WorkingScheduleRevision.objects.filter(owner=owner, effective_from__lte=effective_from).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=effective_from)
    ).prefetch_related("windows").first()
    windows = [{"weekday": item.weekday, "start_time": item.start_time, "end_time": item.end_time,
                "ends_next_day": bool(item.end_day_offset)} for item in revision.windows.all()] if revision else []
    return {"header": {"effective_from": effective_from, "no_windows": revision is not None and not windows},
            "windows": windows}


def working_window_screen(*, owner, anchor):
    """Private weekly willingness preview and owned configuration history."""
    _require_date(anchor)
    monday = anchor - timedelta(days=anchor.weekday())
    lower, _ = date_bounds(monday, WORKING_ZONE)
    upper, _ = date_bounds(monday + timedelta(days=7), WORKING_ZONE)
    result = working_windows_for_user(owner=owner, starts_at=lower, ends_at=upper)
    revisions = list(WorkingScheduleRevision.objects.filter(owner=owner).prefetch_related("windows"))
    active = next((item for item in revisions if item.effective_from <= anchor
                   and (item.effective_until is None or anchor < item.effective_until)), None)
    days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        start, end = date_bounds(day, WORKING_ZONE)
        bounds = Interval(start, end)
        issues = tuple(issue for issue in result.issues if clip_intervals([issue.affected], bounds))
        days.append({"date": day, "intervals": clip_intervals(result.intervals, bounds) if not issues else (),
                     "issues": issues})
    return {
        "anchor": anchor, "monday": monday, "sunday": monday + timedelta(days=6),
        "previous": monday - timedelta(days=7) if monday.year > 2 else None,
        "next": monday + timedelta(days=7) if monday.year < 9998 else None,
        "days": days, "adjustments": result.adjustments, "active": active, "revisions": revisions,
        "rules": [{"weekday": day_name[weekday],
                   "windows": [item for item in active.windows.all() if item.weekday == weekday] if active else []}
                  for weekday in range(7)],
        "overrides": WorkingDateOverride.objects.filter(owner=owner).prefetch_related("intervals").order_by("-local_date"),
    }


def _require_date(value):
    if not isinstance(value, date) or isinstance(value, datetime) or not 1 < value.year < 9999:
        raise ValidationError("Provide a calendar date between years 0002 and 9998.")


def _window_rows(revision, windows):
    try:
        windows = list(windows)
    except TypeError:
        raise ValidationError("Provide a list of working windows (which may be empty).")
    rows, seen = [], set()
    for spec in windows:
        if not isinstance(spec, WindowSpec):
            raise ValidationError("Each working window must be a WindowSpec.")
        if type(spec.weekday) is not int or not 0 <= spec.weekday <= 6:
            raise ValidationError("Choose weekdays from Monday (0) to Sunday (6).")
        if type(spec.end_day_offset) is not int or spec.end_day_offset not in (0, 1):
            raise ValidationError("A window must end on the same or following date.")
        for clock in (spec.start_time, spec.end_time):
            if not isinstance(clock, time) or clock.tzinfo is not None:
                raise ValidationError("Provide local clock times without a UTC offset.")
        if spec.end_day_offset == 0 and spec.end_time <= spec.start_time:
            raise ValidationError("End must follow start, or select the following day.")
        if spec in seen:
            raise ValidationError("Remove duplicate working windows.")
        seen.add(spec)
        rows.append(WorkingWindow(
            revision=revision, weekday=spec.weekday, start_time=spec.start_time,
            end_time=spec.end_time, end_day_offset=spec.end_day_offset,
        ))
    return rows


@transaction.atomic
def set_working_schedule(*, owner, effective_from, windows):
    """Set the entire weekly pattern from a date, preserving earlier rules.

    Initial setup can describe a past schedule. Subsequent all-future changes
    must be today or later; date-specific overrides allow explicit corrections.
    An empty pattern intentionally offers no weekly working hours.
    """
    _require_date(effective_from)
    lock_schedule_owner(owner)
    revisions = WorkingScheduleRevision.objects.filter(owner=owner)
    if revisions.exists() and effective_from < timezone.now().astimezone(ZoneInfo(WORKING_ZONE)).date():
        raise ValidationError("Choose today or a future date to preserve earlier schedules.")
    previous = revisions.filter(effective_from__lte=effective_from).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=effective_from)
    ).first()
    successor = WorkingScheduleRevision(
        owner=owner, effective_from=effective_from,
        time_zone=previous.time_zone if previous else WORKING_ZONE,
        dst_gap_policy=previous.dst_gap_policy if previous else "shift_forward",
        dst_fold_policy=previous.dst_fold_policy if previous else "first",
    )
    rows = _window_rows(successor, windows)
    successor.full_clean(validate_constraints=False)
    revisions.filter(effective_from__gte=effective_from).delete()
    if previous and previous.effective_from < effective_from:
        previous.effective_until = effective_from
        previous.save(update_fields=["effective_until"])
    successor.full_clean()
    successor.save()
    WorkingWindow.objects.bulk_create(rows)
    return successor


@transaction.atomic
def set_working_date_override(*, owner, local_date, intervals):
    """Replace a full Halifax date; an empty list closes that date for work."""
    _require_date(local_date)
    lock_schedule_owner(owner)
    lower, upper = date_bounds(local_date, WORKING_ZONE)
    try:
        intervals = list(intervals)
    except TypeError:
        raise ValidationError("Provide a list of intervals (which may be empty).")
    if any(not isinstance(item, Interval) for item in intervals):
        raise ValidationError("Provide aware Interval values.")
    if any(item.starts_at < lower or item.ends_at > upper for item in intervals):
        raise ValidationError("Override intervals must lie inside the complete local date.")
    override, _ = WorkingDateOverride.objects.get_or_create(
        owner=owner, local_date=local_date, defaults={"time_zone": WORKING_ZONE},
    )
    override.intervals.all().delete()
    OverrideInterval.objects.bulk_create([
        OverrideInterval(override=override, starts_at=item.starts_at, ends_at=item.ends_at)
        for item in merge_intervals(intervals)
    ])
    return override


@transaction.atomic
def remove_working_date_override(*, owner, override_id):
    """Restore the normal weekly rule for this owned date."""
    lock_schedule_owner(owner)
    override = WorkingDateOverride.objects.filter(owner=owner, pk=override_id).first()
    if override is None:
        raise PermissionDenied
    override.delete()


def working_windows_for_user(*, owner, starts_at, ends_at):
    """Expand weekly rules, then replace full dates, including overnight carry-in."""
    bounds = query_interval(starts_at, ends_at)
    first = bounds.starts_at.date() - timedelta(days=3)
    until = bounds.ends_at.date() + timedelta(days=3)
    revisions = WorkingScheduleRevision.objects.filter(
        owner=owner, effective_from__lt=until,
    ).filter(Q(effective_until__isnull=True) | Q(effective_until__gt=first)).prefetch_related("windows")
    intervals, adjustments, issues = [], [], []
    for revision in revisions:
        lower, upper = max(first, revision.effective_from), min(until, revision.effective_until or until)
        for window in revision.windows.all():
            first_ordinal = lower.toordinal() + (window.weekday - lower.weekday()) % 7
            for ordinal in range(first_ordinal, upper.toordinal(), 7):
                day = date.fromordinal(ordinal)
                start = resolve_local_time(
                    datetime.combine(day, window.start_time), revision.time_zone,
                    gap_policy=revision.dst_gap_policy, fold_policy=revision.dst_fold_policy,
                )
                end = resolve_local_time(
                    datetime.combine(day + timedelta(days=window.end_day_offset), window.end_time),
                    revision.time_zone, gap_policy=revision.dst_gap_policy, fold_policy=revision.dst_fold_policy,
                )
                resolution = WorkingResolution(window.pk, day, start, end)
                if end.value.astimezone(UTC) <= start.value.astimezone(UTC):
                    affected = resolution_affected_dates(start, end)
                    for part in clip_intervals([affected], bounds):
                        issues.append(WorkingIssue(resolution, part))
                else:
                    parts = clip_intervals([Interval(start.value, end.value)], bounds)
                    intervals.extend(parts)
                    if parts and (start.adjustment or end.adjustment):
                        adjustments.append(resolution)

    overrides = WorkingDateOverride.objects.filter(
        owner=owner, local_date__gte=first, local_date__lt=until,
    ).prefetch_related("intervals")
    for override in overrides:
        lower, upper = date_bounds(override.local_date, override.time_zone)
        if upper <= lower:  # A skipped local date has no instants to replace.
            continue
        day_interval = Interval(lower, upper)
        intervals = list(subtract_intervals(intervals, [day_interval]))
        intervals.extend(clip_intervals([
            Interval(item.starts_at, item.ends_at) for item in override.intervals.all()
        ], bounds))
        # A date override can explicitly resolve an invalid working rule.
        issues = [WorkingIssue(issue.resolution, part)
                  for issue in issues for part in subtract_intervals([issue.affected], [day_interval])]
        adjustments = [item for item in adjustments
                       if not (item.start_resolution.value.astimezone(UTC) >= lower
                               and item.end_resolution.value.astimezone(UTC) <= upper)]
    return WorkingWindowResult(merge_intervals(intervals), tuple(adjustments), tuple(issues))
