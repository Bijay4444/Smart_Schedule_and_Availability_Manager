"""Read-only, owner-scoped adapters. The model never queries the database directly."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError

from scheduling.availability import availability_for_user, check_proposed_shift
from scheduling.calendar import calendar_date
from scheduling.intervals import date_bounds
from scheduling.time_resolution import resolve_local_time

ZONE = ZoneInfo("America/Halifax")


def definition(name, description, properties):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": list(properties), "additionalProperties": False},
    }}


TOOLS = [
    definition("read_work_availability", "Return an authoritative work-availability report with correct weekdays, daily intervals and total. Use for availability reports, including employer copy text. Inclusive range at most 31 days. No private titles are returned.", {
        "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
        "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
    }),
    definition("read_schedule", "Read commitments, working windows, work availability and overlapping commitments for inclusive local dates (maximum 31 days). Includes review metadata. Filter by source only after reading results; availability always accounts for ALL sources.", {
        "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
        "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
    }),
    definition("check_shift", "Check an unsaved proposed shift. Never saves anything. Use local Halifax clock labels without offsets. Missing times shift forward and repeated times use the first occurrence; explain adjustments.", {
        "starts_at": {"type": "string", "description": "YYYY-MM-DDTHH:MM without offset"},
        "ends_at": {"type": "string", "description": "YYYY-MM-DDTHH:MM without offset; explicit next date for overnight"},
    }),
]


def interval(item):
    return {"starts_at": item.starts_at.astimezone(ZONE).isoformat(),
            "ends_at": item.ends_at.astimezone(ZONE).isoformat(),
            "minutes": (item.ends_at - item.starts_at).total_seconds() / 60}


def commitment(item):
    return {**interval(item), "title": item.title, "source": item.source.name}


def snapshot(result):
    # Refuse oversized results rather than silently suggesting a partial schedule is complete.
    if len(result.commitments) + len(result.available) + len(result.working_windows) > 200:
        raise ValidationError("Too many results. Ask for a shorter date range.")
    return {
        "timezone": ZONE.key, "complete": result.complete,
        "commitments": [commitment(item) for item in result.commitments],
        "working_windows": [interval(item) for item in result.working_windows],
        "work_availability": [interval(item) for item in result.available],
        "available_minutes": sum((i.ends_at - i.starts_at).total_seconds() / 60 for i in result.available),
        "needs_review": [interval(item) for item in result.withheld],
        "clock_adjustments": bool(result.adjustments) or any(
            getattr(item, "start_resolution", None) and (
                item.start_resolution.adjustment or item.end_resolution.adjustment
            ) for item in result.commitments
        ),
    }


def execute_tool(*, owner, name, arguments):
    if not isinstance(arguments, dict):
        raise ValidationError("Tool arguments must be an object.")
    expected = {"read_schedule": {"start_date", "end_date"},
                "read_work_availability": {"start_date", "end_date"},
                "check_shift": {"starts_at", "ends_at"}}
    if name not in expected or set(arguments) != expected[name]:
        raise ValidationError("Unsupported tool or arguments.")
    if not all(isinstance(v, str) and len(v) <= 32 for v in arguments.values()):
        raise ValidationError("Provide date/time strings.")
    if name == "read_work_availability":
        from .availability_answers import availability_answer
        return {"answer": availability_answer(owner=owner, first=calendar_date(arguments["start_date"]), last=calendar_date(arguments["end_date"]))}
    if name == "read_schedule":
        first, last = calendar_date(arguments["start_date"]), calendar_date(arguments["end_date"])
        if not 0 <= (last - first).days < 31:
            raise ValidationError("Choose between 1 and 31 inclusive dates.")
        start, _ = date_bounds(first, ZONE.key)
        _, end = date_bounds(last, ZONE.key)
        result = availability_for_user(owner=owner, starts_at=start, ends_at=end)
        data = snapshot(result)
        # Strict overlaps: touching boundaries are not conflicts. Python computes pairs.
        data["conflicts"] = [
            {"first": commitment(left), "second": commitment(right)}
            for index, left in enumerate(result.commitments)
            for right in result.commitments[index + 1:]
            if left.starts_at < right.ends_at and right.starts_at < left.ends_at
        ]
        if len(data["conflicts"]) > 100:
            raise ValidationError("Too many conflicts. Ask for a shorter range.")
        data.update(start_date=first.isoformat(), end_date=last.isoformat())
        return data
    resolved = []
    for key in ("starts_at", "ends_at"):
        try:
            local = datetime.fromisoformat(arguments[key])
        except ValueError:
            raise ValidationError("Provide local date/time labels in ISO format.")
        resolved.append(resolve_local_time(local, ZONE.key))
    start, end = (item.value for item in resolved)
    if not timedelta(0) < end.astimezone(ZoneInfo("UTC")) - start.astimezone(ZoneInfo("UTC")) <= timedelta(days=7):
        raise ValidationError("A proposed shift must last between zero and seven days (positive duration).")
    check = check_proposed_shift(owner=owner, starts_at=start, ends_at=end)
    return {**snapshot(check.availability), "is_available": check.is_available,
            "outside_working_windows": [interval(item) for item in check.outside_working_windows],
            "conflicting_commitments": [commitment(item) for item in check.conflicts],
            "resolved_shift": {"starts_at": start.isoformat(), "ends_at": end.isoformat()},
            "adjustments": [item.adjustment for item in resolved]}
