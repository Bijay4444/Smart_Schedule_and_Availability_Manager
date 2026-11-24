"""Present a read-only shift check without adding scheduling rules to views."""

from datetime import UTC
from zoneinfo import ZoneInfo

from .availability import check_proposed_shift
from .intervals import resolution_affected_dates
from .working_windows import WORKING_ZONE


def _label(value):
    # Keep optional input seconds/fractions instead of rounding the checked shift.
    clock = value.time().isoformat(timespec="microseconds" if value.microsecond else "seconds" if value.second else "minutes")
    if value.microsecond:
        clock = clock.rstrip("0")
    return f"{value:%a %d %b %Y}, {clock} {value.tzname()}"


def _display_interval(starts_at, ends_at, zone):
    start, end = starts_at.astimezone(zone), ends_at.astimezone(zone)
    return {"starts_at": start, "ends_at": end, "start_label": _label(start), "end_label": _label(end)}


def shift_screen_for_user(*, owner, starts_at, ends_at):
    check = check_proposed_shift(owner=owner, starts_at=starts_at, ends_at=ends_at)
    zone = ZoneInfo(WORKING_ZONE)
    conflicts = [{
        "title": item.title, "source": item.source.name,
        **_display_interval(item.starts_at, item.ends_at, zone),
        "date": max(item.starts_at.astimezone(UTC), starts_at.astimezone(UTC)).astimezone(zone).date(),
    } for item in check.conflicts]
    review_working = sorted({item.affected.starts_at.astimezone(zone).date()
                             for item in check.availability.working_issues})
    review_commitments = sorted({resolution_affected_dates(item.start_resolution, item.end_resolution)
                                .starts_at.astimezone(zone).date()
                                for item in check.availability.commitment_issues})
    # A known conflict remains a conflict even if another part needs review.
    # An incomplete calculation can never report the shift as available.
    return {
        "available": check.is_available, "complete": check.complete,
        **_display_interval(starts_at, ends_at, zone),
        "date": starts_at.astimezone(zone).date(), "conflicts": conflicts,
        "outside": tuple(_display_interval(item.starts_at, item.ends_at, zone)
                         for item in check.outside_working_windows),
        "review_working": review_working, "review_commitments": review_commitments,
    }
