"""Resolve local clock labels without treating missing times as real instants."""

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class ResolvedTime:
    requested: datetime  # Local clock label, without an offset.
    value: datetime  # Valid local time with the schedule's zone attached.
    adjustment: str | None = None


def resolve_local_time(
    local_time, time_zone, *, gap_policy="shift_forward", fold_policy="first"
):
    """Round-trip both folds through UTC to distinguish normal, repeated, and missing times.

    Gap resolution uses the zone's actual offset change, including non-hour
    changes. The returned metadata lets the frontend explain automatic choices.
    """
    if not isinstance(local_time, datetime) or local_time.tzinfo is not None:
        raise ValidationError("Provide a local datetime without a UTC offset.")
    if gap_policy != "shift_forward" or fold_policy != "first":
        raise ValidationError("Unsupported daylight-saving policy.")
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValidationError("Choose a valid IANA time zone.")

    # A caller's fold flag must not override the revision's explicit policy.
    local_time = local_time.replace(fold=0)
    candidates = {}
    round_trips = []
    for fold in (0, 1):
        tentative = local_time.replace(tzinfo=zone, fold=fold)
        instant = tentative.astimezone(UTC)
        returned = instant.astimezone(zone)
        round_trips.append(returned)
        if returned.replace(tzinfo=None) == local_time:
            candidates[instant] = returned

    if candidates:
        first = candidates[min(candidates)]
        return ResolvedTime(
            local_time, first, "fold_first" if len(candidates) == 2 else None
        )

    # In a forward gap, the pre-transition offset round-trips to the requested
    # label plus the gap. This preserves minutes rather than snapping to its end.
    forward = [value for value in round_trips if value.replace(tzinfo=None) > local_time]
    if not forward:
        raise ValidationError("This local time could not be resolved; review this date.")
    resolved = min(forward, key=lambda value: value.replace(tzinfo=None))
    return ResolvedTime(local_time, resolved, "gap_shift_forward")
