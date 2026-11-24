"""Project calculated availability into a visual week and private-detail-free text."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone

from .availability import weekly_availability_for_user
from .intervals import date_bounds, resolution_affected_dates
from .time_resolution import resolve_local_time
from .working_windows import WORKING_ZONE


@dataclass(frozen=True)
class AvailabilitySlot:
    starts_at: datetime
    ends_at: datetime
    start_label: str
    end_label: str
    left_percent: str
    width_percent: str


@dataclass(frozen=True)
class AvailabilityDisplayDay:
    date: date
    complete: bool
    slots: tuple[AvailabilitySlot, ...]
    axis: tuple[dict, ...]
    elapsed_hours: int
    review_working: bool
    review_commitments: bool


def _duration_label(value):
    total = (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds
    hours, rest = divmod(total, 3600_000_000)
    minutes, rest = divmod(rest, 60_000_000)
    seconds, micros = divmod(rest, 1_000_000)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or micros:
        label = f"{seconds}.{micros:06}".rstrip("0").rstrip(".") if micros else str(seconds)
        parts.append(f"{label}s")
    return " ".join(parts) or "0m"


def _repeated(instant):
    return instant.replace(fold=0).utcoffset() != instant.replace(fold=1).utcoffset()


def _clock_label(instant, next_midnight, include_zone):
    if instant.astimezone(UTC) == next_midnight:
        label = "24:00"
    else:
        precision = "microseconds" if instant.microsecond else "seconds" if instant.second else "minutes"
        label = instant.time().isoformat(timespec=precision)
        if instant.microsecond:
            label = label.rstrip("0")
    return f"{label} {instant.tzname()}" if include_zone else label


def _day_axis(day, lower, upper):
    marks = []
    for hour in (0, 6, 12, 18, 24):
        value = upper if hour == 24 else resolve_local_time(datetime.combine(day, time(hour)), WORKING_ZONE).value.astimezone(UTC)
        percent = 100 * (value - lower) / (upper - lower)
        marks.append({"label": f"{hour:02}:00", "percent": format(percent, ".8f")})
    return tuple(marks)


def employer_availability_text(*, starts_on, days, complete):
    """Only accept the display projection: no source, title, or account fields."""
    ends_on = starts_on + timedelta(days=6)
    lines = [f"Work availability: {starts_on:%d %b %Y} – {ends_on:%d %b %Y}",
             f"Time zone: {WORKING_ZONE}"]
    if not complete:
        lines.append("Draft: availability is not confirmed for dates marked Needs review.")
    lines.append("")
    for day in days:
        if not day.complete:
            hours = "Needs review — availability not confirmed"
        else:
            hours = ", ".join(f"{item.start_label}–{item.end_label}" for item in day.slots) or "Unavailable"
        lines.append(f"{day.date:%a %d %b}: {hours}")
    return "\n".join(lines)


def availability_screen_for_user(*, owner, anchor=None):
    """Read once, then discard commitment details before rendering or copying."""
    zone = ZoneInfo(WORKING_ZONE)
    anchor = anchor or timezone.localdate(timezone.now(), zone)
    if isinstance(anchor, date) and not isinstance(anchor, datetime):
        if (anchor - timedelta(days=anchor.weekday())).year <= 1:
            raise ValidationError("This week is outside the supported calendar range.")
    week = weekly_availability_for_user(owner=owner, anchor=anchor)
    working_issues = [issue.affected for issue in week.result.working_issues]
    commitment_issues = [resolution_affected_dates(issue.start_resolution, issue.end_resolution)
                         for issue in week.result.commitment_issues]
    days, total = [], timedelta()
    for day in week.days:
        lower, upper = date_bounds(day.local_date, WORKING_ZONE)
        duration = upper - lower
        slots = []
        for item in day.intervals:
            start, end = item.starts_at.astimezone(zone), item.ends_at.astimezone(zone)
            show_zone = _repeated(start) or _repeated(end) or start.utcoffset() != end.utcoffset()
            slots.append(AvailabilitySlot(
                item.starts_at, item.ends_at, _clock_label(start, upper, show_zone), _clock_label(end, upper, show_zone),
                format(100 * (item.starts_at - lower) / duration, ".8f"),
                format(100 * (item.ends_at - item.starts_at) / duration, ".8f"),
            ))
            total += item.ends_at - item.starts_at
        days.append(AvailabilityDisplayDay(
            day.local_date, day.complete, tuple(slots), _day_axis(day.local_date, lower, upper),
            int(duration.total_seconds() / 3600),
            any(item.starts_at < upper and item.ends_at > lower for item in working_issues),
            any(item.starts_at < upper and item.ends_at > lower for item in commitment_issues),
        ))
    days = tuple(days)
    previous = week.starts_on - timedelta(days=7)
    following = week.starts_on + timedelta(days=7)
    return {
        "starts_on": week.starts_on, "ends_on": week.starts_on + timedelta(days=6), "days": days,
        "previous": previous if previous.year > 1 else None,
        "next": following if following.year < 9999 else None,
        "complete": week.complete, "total_label": _duration_label(total),
        "available_day_count": sum(bool(day.slots) for day in days),
        "has_working_windows": bool(week.result.working_windows),
        "share_text": employer_availability_text(starts_on=week.starts_on, days=days, complete=week.complete),
    }
