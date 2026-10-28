"""Build a private weekly presentation from one-time and recurring commitments."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Commitment, CommitmentSource
from .recurrence import occurrences_for_user
from .time_resolution import resolve_local_time


DISPLAY_ZONE = "America/Halifax"


def calendar_date(value):
    """Accept canonical ISO dates; keep week navigation inside safe date bounds."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError("Choose a date in YYYY-MM-DD format.")
    if parsed.isoformat() != value or not 1 < parsed.year < 9999:
        raise ValidationError("Choose a date between years 0002 and 9998.")
    return parsed


@dataclass
class CalendarEntry:
    key: tuple
    title: str
    source: CommitmentSource
    starts_at: datetime
    ends_at: datetime
    kind: str
    commitment_id: int | None = None
    adjustments: tuple[str, ...] = ()
    has_conflict: bool = False


@dataclass
class CalendarBlock:
    entry: CalendarEntry
    starts_at: datetime
    ends_at: datetime
    start_label: str
    end_label: str
    top_minutes: float
    height_minutes: float
    continues_before: bool
    continues_after: bool
    left_percent: str = "0"
    width_percent: str = "100"


@dataclass
class CalendarDay:
    date: date
    is_today: bool
    minutes: float
    hours: list
    blocks: list[CalendarBlock] = field(default_factory=list)

    @property
    def length_hours(self):
        return round(self.minutes / 60)


def _midnight(day):
    return resolve_local_time(datetime.combine(day, time.min), DISPLAY_ZONE).value.astimezone(UTC)


def _label(instant):
    # Offset abbreviations distinguish the two 01:30 labels on a fall-back date.
    return instant.astimezone(ZoneInfo(DISPLAY_ZONE)).strftime("%H:%M %Z")


def _assign_lanes(blocks):
    """Pack connected visual overlaps; short cards still need readable labels."""
    active, group = [], []
    column_count = 0

    def finish_group():
        for block, column in group:
            block.left_percent = format(100 * column / column_count, ".5f")
            block.width_percent = format(100 / column_count, ".5f")

    for block in blocks:
        active = [(end, column) for end, column in active if end > block.top_minutes]
        if not active and group:
            finish_group()
            group = []
            column_count = 0
        used = {column for _, column in active}
        column = next(index for index in range(len(used) + 1) if index not in used)
        active.append((block.top_minutes + max(block.height_minutes, 60), column))
        group.append((block, column))
        column_count = max(column_count, column + 1)
    if group:
        finish_group()


def calendar_for_user(*, owner, anchor=None):
    today = timezone.localdate(timezone.now(), ZoneInfo(DISPLAY_ZONE))
    anchor = anchor or today
    if not isinstance(anchor, date) or isinstance(anchor, datetime):
        raise ValidationError("Choose a calendar date.")
    monday = anchor - timedelta(days=anchor.weekday())
    if not 1 < monday.year < 9999:
        raise ValidationError("This week is outside the supported calendar range.")
    following = monday + timedelta(days=7)
    start, end = _midnight(monday), _midnight(following)
    recurring = occurrences_for_user(owner=owner, starts_at=start, ends_at=end)
    entries = [CalendarEntry(
        ("one_time", item.pk), item.title, item.source,
        item.starts_at.astimezone(UTC), item.ends_at.astimezone(UTC), "One-time", item.pk,
    ) for item in Commitment.objects.filter(
        source__owner=owner, starts_at__lt=end, ends_at__gt=start
    ).select_related("source")]
    for item in recurring.occurrences:
        notes = []
        for endpoint, resolved in (("Start", item.start_resolution), ("End", item.end_resolution)):
            if resolved and resolved.adjustment:
                explanation = (
                    "moved forward for the clock change" if resolved.adjustment == "gap_shift_forward"
                    else "uses the first repeated clock time"
                )
                notes.append(f"{endpoint} {explanation}: {_label(resolved.value)}.")
        entries.append(CalendarEntry(
            ("recurring", *item.key), item.title, item.source, item.starts_at, item.ends_at,
            "Rescheduled" if item.is_replacement else "Weekly", adjustments=tuple(notes),
        ))
    entries.sort(key=lambda item: (item.starts_at, item.ends_at, item.key))
    active = []
    for item in entries:
        active = [previous for previous in active if previous.ends_at > item.starts_at]
        for previous in active:
            previous.has_conflict = item.has_conflict = True
        active.append(item)

    days = []
    for offset in range(7):
        local_date = monday + timedelta(days=offset)
        day_start, day_end = _midnight(local_date), _midnight(local_date + timedelta(days=1))
        minutes = (day_end - day_start).total_seconds() / 60
        hours = [{"minute": minute, "label": (day_start + timedelta(minutes=minute)).astimezone(ZoneInfo(DISPLAY_ZONE)).strftime("%H:%M")}
                 for minute in range(0, int(minutes), 60)]
        day = CalendarDay(local_date, local_date == today, minutes, hours)
        for item in entries:
            clipped_start, clipped_end = max(item.starts_at, day_start), min(item.ends_at, day_end)
            if clipped_start >= clipped_end:
                continue
            day.blocks.append(CalendarBlock(
                item, clipped_start, clipped_end, _label(clipped_start),
                "24:00" if clipped_end == day_end else _label(clipped_end),
                (clipped_start - day_start).total_seconds() / 60,
                (clipped_end - clipped_start).total_seconds() / 60,
                item.starts_at < day_start, item.ends_at > day_end,
            ))
        _assign_lanes(day.blocks)
        days.append(day)
    previous = monday - timedelta(days=7)
    used_sources = {item.source.pk: item.source for item in entries}
    for source in CommitmentSource.objects.filter(owner=owner, archived_at__isnull=True):
        used_sources[source.pk] = source
    earliest = min((block.top_minutes for day in days for block in day.blocks), default=480)
    return {
        "start": monday, "end": following - timedelta(days=1),
        "previous": previous if previous.year > 1 else None,
        "next": following if following.year < 9999 else None,
        "today": today, "days": days,
        "sources": sorted(used_sources.values(), key=lambda item: (item.name, item.pk)),
        "entry_count": len(entries), "conflict_count": sum(item.has_conflict for item in entries),
        "issues": recurring.issues, "complete": recurring.complete,
        "max_minutes": max(day.minutes for day in days),
        "initial_minute": max(0, min(420, earliest - 60)),
    }
