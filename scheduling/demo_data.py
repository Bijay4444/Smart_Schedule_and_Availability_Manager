"""Repeatable fictional schedules for manual feature checks, isolated by account."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .calendar import calendar_date
from .intervals import Interval
from .models import (
    Commitment, CommitmentSource, OccurrenceException, RecurringSeries,
    SeriesRevision, WorkingDateOverride, WorkingScheduleRevision,
)
from .recurrence import (
    cancel_occurrence, create_series, end_series, reschedule_occurrence, revise_series,
)
from .services import archive_source, save_commitment
from .working_windows import (
    WORKING_ZONE, WindowSpec, set_working_date_override, set_working_schedule,
)


DEMO_PASSWORD = "DemoSchedule!2026"
DEMO_MARKER = "smart_schedule_demo_v1"
DEMO_ACCOUNTS = {
    "schedule_demo": "Classes, two employers, personal time, conflicts, and history",
    "schedule_demo_other": "Separate private schedule and a fully occupied workday",
    "schedule_demo_empty": "First-use and empty states; add your own sample data",
    "schedule_demo_dst": "Spring/fall clock changes and unresolved review dates",
}
ZONE = ZoneInfo(WORKING_ZONE)


@dataclass(frozen=True)
class DemoPlan:
    week: date
    changes_on: date

    @property
    def marker(self):
        return f"{DEMO_MARKER}:{self.week.isoformat()}:{self.changes_on.isoformat()}"

    @property
    def spring(self):
        first = date(self.week.year, 3, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7)

    @property
    def fall(self):
        first = date(self.week.year, 11, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7)


@dataclass(frozen=True)
class SeedResult:
    plan: DemoPlan
    created: tuple[str, ...]
    restored: tuple[str, ...]
    unchanged: tuple[str, ...]


def _monday(value):
    return value - timedelta(days=value.weekday())


def _new_plan(week):
    today = timezone.localdate(timezone.now(), ZONE)
    anchor = calendar_date(week) if week is not None else today
    # These fictional DST examples use Halifax's post-2007 transition rules.
    if not 2007 <= anchor.year <= 2099:
        raise ValidationError("Choose a demo week between years 2007 and 2099.")
    monday = _monday(anchor)
    return DemoPlan(monday, max(monday + timedelta(days=7), _monday(today) + timedelta(days=7)))


def _saved_plan(user):
    names = list(user.groups.filter(name__startswith=f"{DEMO_MARKER}:").values_list("name", flat=True))
    if len(names) != 1:
        raise ValidationError(f"Demo account {user.username} has missing or inconsistent seed metadata.")
    try:
        _, week, changes_on = names[0].split(":")
        return DemoPlan(calendar_date(week), calendar_date(changes_on))
    except (ValueError, ValidationError):
        raise ValidationError(f"Demo account {user.username} has invalid seed metadata.")


def _clear_schedule(user):
    """Delete only an explicitly reset demo owner's graph, in protected-FK order."""
    OccurrenceException.objects.filter(series__source__owner=user).delete()
    SeriesRevision.objects.filter(series__source__owner=user).delete()
    RecurringSeries.objects.filter(source__owner=user).delete()
    Commitment.objects.filter(source__owner=user).delete()
    CommitmentSource.objects.filter(owner=user).delete()
    WorkingDateOverride.objects.filter(owner=user).delete()
    WorkingScheduleRevision.objects.filter(owner=user).delete()


@transaction.atomic
def seed_demo(*, week=None, reset=False):
    """Create missing demo accounts, or explicitly restore their whole fixture set.

    A marker group distinguishes seed-owned users from real username collisions.
    Its row lock serializes concurrent seed commands. The entire operation rolls
    back on any failure, including fixture errors or protected cross-owner data.
    """
    marker, _ = Group.objects.get_or_create(name=DEMO_MARKER)
    Group.objects.select_for_update().get(pk=marker.pk)
    existing = {user.username: user for user in get_user_model().objects.select_for_update().filter(
        username__in=DEMO_ACCOUNTS).order_by("pk")}
    for user in existing.values():
        if not user.groups.filter(pk=marker.pk).exists():
            raise ValidationError(f"Account {user.username} already exists and is not seed-owned. No data was changed.")
    plans = {_saved_plan(user) for user in existing.values()}
    if len(plans) > 1:
        raise ValidationError("Demo accounts belong to different seed runs; no data was changed.")
    saved = next(iter(plans), None)
    requested = _new_plan(week if week is not None else saved.week.isoformat() if saved else None)
    if saved and week is not None and requested.week != saved.week and not reset:
        raise ValidationError("Demo accounts already use another week. Use --reset with --week to move them.")
    plan = requested if reset or not saved else saved
    if ("schedule_demo" not in existing and saved and not reset
            and plan.changes_on < timezone.localdate(timezone.now(), ZONE)):
        raise ValidationError("The main demo account is missing and its history is now past. Use --reset to rebuild the demo set.")
    date_marker, _ = Group.objects.get_or_create(name=plan.marker)
    created, restored, unchanged = [], [], []
    builders = {"schedule_demo": _main_schedule, "schedule_demo_other": _other_schedule,
                "schedule_demo_empty": lambda user, plan: None, "schedule_demo_dst": _dst_schedule}
    for username in DEMO_ACCOUNTS:
        user = existing.get(username)
        if user and not reset:
            unchanged.append(username)
            continue
        if user:
            _clear_schedule(user)
            user.groups.clear()
            user.user_permissions.clear()
            restored.append(username)
        else:
            user = get_user_model()(username=username)
            created.append(username)
        user.first_name = "Demo"
        user.last_name = {"schedule_demo": "Schedule", "schedule_demo_other": "Privacy",
                          "schedule_demo_empty": "Empty", "schedule_demo_dst": "Clock changes"}[username]
        user.email = ""
        user.is_active, user.is_staff, user.is_superuser = True, False, False
        user.set_password(DEMO_PASSWORD)
        user.full_clean(exclude=["password"])
        user.save()
        user.groups.add(marker, date_marker)
        builders[username](user, plan)
    # Remove only orphaned metadata for this seed version, never other groups.
    Group.objects.filter(name__startswith=f"{DEMO_MARKER}:", user__isnull=True).delete()
    return SeedResult(plan, tuple(created), tuple(restored), tuple(unchanged))


def _source(user, name, color):
    source = CommitmentSource(owner=user, name=name, color=color)
    source.full_clean()
    source.save()
    return source


def _instant(day, hour, minute=0, *, fold=0):
    return datetime.combine(day, time(hour, minute), ZONE).replace(fold=fold)


def _one_time(user, source, title, day, start, end, *, end_day=None):
    return save_commitment(owner=user, confirm_conflicts=True, commitment=Commitment(
        source=source, title=title, starts_at=_instant(day, *start),
        ends_at=_instant(end_day or day, *end),
    ))


def _series(user, source, title, start, weekdays, clocks, **extra):
    return create_series(owner=user, source_id=source.pk, title=title, starts_on=start,
                         weekdays=weekdays, start_time=time(*clocks[0]), end_time=time(*clocks[1]), **extra)


def _main_schedule(user, plan):
    week, changes = plan.week, plan.changes_on
    classes = _source(user, "Demo · Classes", "#315c52")
    job_a = _source(user, "Demo · Job A", "#835328")
    job_b = _source(user, "Demo · Job B", "#6550a1")
    personal = _source(user, "Demo · Personal", "#245b88")
    retired = _source(user, "Demo · Former employer (archived)", "#756657")
    windows = [WindowSpec(0, time(8), time(20)), WindowSpec(1, time(8), time(18)),
               WindowSpec(2, time(8), time(20)), WindowSpec(3, time(8), time(12)),
               WindowSpec(3, time(14), time(18)), WindowSpec(4, time(8), time(22)),
               WindowSpec(5, time(9), time(17)), WindowSpec(6, time(22), time(6), 1)]
    set_working_schedule(owner=user, effective_from=week - timedelta(days=7), windows=windows)
    set_working_schedule(owner=user, effective_from=changes,
                         windows=[WindowSpec(0, time(9), time(19)), *windows[1:]])
    set_working_date_override(owner=user, local_date=week + timedelta(days=3), intervals=[])
    saturday = week + timedelta(days=5)
    set_working_date_override(owner=user, local_date=saturday, intervals=[
        Interval(_instant(saturday, 10), _instant(saturday, 14)),
        Interval(_instant(saturday, 15), _instant(saturday, 17)),
    ])
    # Close a later Monday, including Sunday's overnight carry-in.
    set_working_date_override(owner=user, local_date=changes + timedelta(days=7), intervals=[])

    _series(user, classes, "Demo · Weekly class", week, [0, 2], ((10, 0), (12, 0)))
    job_a_series = _series(user, job_a, "Demo · Job A shift", week, [1, 3], ((9, 0), (13, 0)))
    job_b_series = _series(user, job_b, "Demo · Job B shift", week, [4], ((16, 0), (20, 0)))
    personal_series = _series(user, personal, "Demo · Protected personal time", week, [2], ((17, 0), (18, 0)))
    _series(user, job_a, "Demo · Sunday overnight", week - timedelta(days=1), [6],
            ((22, 0), (6, 0)), end_day_offset=1, ends_on=week + timedelta(days=6))
    _series(user, retired, "Demo · Archived Saturday shift", week, [5], ((11, 0), (12, 0)))
    for original in (week + timedelta(days=1), changes + timedelta(days=1)):
        moved = original + timedelta(days=1)
        reschedule_occurrence(owner=user, series_id=job_a_series.pk, original_start_date=original,
                              replacement_source_id=job_a.pk, replacement_title="Demo · Moved Job A shift",
                              starts_at=_instant(moved, 14), ends_at=_instant(moved, 16))
    cancel_occurrence(owner=user, series_id=personal_series.pk, original_start_date=week + timedelta(days=2))
    revise_series(owner=user, series_id=job_a_series.pk, effective_from=changes,
                  title="Demo · Job A revised hours", weekdays=[1, 3], start_time=time(10), end_time=time(14))
    revise_series(owner=user, series_id=job_b_series.pk, effective_from=changes,
                  title="Demo · Job B revised hours", weekdays=[4], start_time=time(17), end_time=time(21))
    end_series(owner=user, series_id=job_a_series.pk, ends_before=changes + timedelta(days=14))

    _one_time(user, personal, "Demo · Protected study", week, (12, 0), (14, 0))
    _one_time(user, job_b, "Demo · Conflicting training", week + timedelta(days=2), (11, 0), (13, 0))
    _one_time(user, retired, "Demo · Archived handover", week + timedelta(days=1), (15, 0), (16, 0))
    _one_time(user, personal, "Demo · Protected errands", saturday, (12, 30), (14, 0))
    _one_time(user, job_b, "Demo · One-time overnight", week + timedelta(days=6), (23, 0), (2, 0),
              end_day=week + timedelta(days=7))
    archive_source(owner=user, source_id=retired.pk)


def _other_schedule(user, plan):
    work = _source(user, "Demo · Other account employer", "#6550a1")
    set_working_schedule(owner=user, effective_from=plan.week, windows=[
        WindowSpec(0, time(8), time(17)), WindowSpec(4, time(9), time(17)),
    ])
    _one_time(user, work, "Demo · Private other-account shift", plan.week, (9, 0), (10, 0))
    _one_time(user, work, "Demo · Fully occupied Friday", plan.week + timedelta(days=4), (9, 0), (17, 0))


def _dst_schedule(user, plan):
    source = _source(user, "Demo · Clock-change commitments", "#835328")
    set_working_schedule(owner=user, effective_from=date(plan.week.year, 1, 1), windows=[
        WindowSpec(6, time(0), time(6)), WindowSpec(6, time(2, 15), time(4)),
        WindowSpec(6, time(2, 30), time(3)),
    ])
    _series(user, source, "Demo · Spring shifted time", plan.spring, [6], ((2, 15), (4, 0)), ends_on=plan.spring)
    _series(user, source, "Demo · Spring commitment needs review", plan.spring, [6],
            ((2, 30), (3, 0)), ends_on=plan.spring)
    _series(user, source, "Demo · First repeated time", plan.fall, [6], ((1, 15), (2, 0)), ends_on=plan.fall)
    save_commitment(owner=user, confirm_conflicts=True, commitment=Commitment(
        source=source, title="Demo · Both repeated hours", starts_at=_instant(plan.fall, 1, 15),
        ends_at=_instant(plan.fall, 1, 45, fold=1),
    ))
    day_after = plan.fall + timedelta(days=1)
    set_working_date_override(owner=user, local_date=day_after, intervals=[
        Interval(_instant(day_after, 8), _instant(day_after, 10)),
    ])


def demo_walkthrough(result):
    """Print real dates/URLs so a tester does not need to calculate offsets."""
    plan, root = result.plan, "http://127.0.0.1:8000"
    week, change = plan.week, plan.changes_on
    lines = [
        "Fictional local demo data. All times use America/Halifax.",
        f"Demo week: {week} through {week + timedelta(days=6)}; future changes: {change}.",
        f"Created: {', '.join(result.created) or 'none'}",
        f"Reset: {', '.join(result.restored) or 'none'}",
        f"Unchanged: {', '.join(result.unchanged) or 'none'}",
        f"Seed login password: {DEMO_PASSWORD} (unchanged accounts keep any password you set).",
        "Expected baseline outcomes follow; your manual edits may change them until --reset.",
        "Accounts:", *[f"  {username}: {purpose}" for username, purpose in DEMO_ACCOUNTS.items()],
        "", "MAIN ACCOUNT: schedule_demo", f"  Calendar: {root}/week/?week={week}",
        f"  Availability/copy: {root}/availability/?week={week}",
        "  Monday: 08:00–10:00 and 14:00–20:00 before the planned future change.",
        f"  Wednesday {week + timedelta(days=2)}: overlapping class/training; moved Job A 14:00–16:00; personal time cancelled.",
        f"  Thursday {week + timedelta(days=3)}: closed for work, even though commitments remain.",
        f"  Saturday {week + timedelta(days=5)}: override 10:00–14:00, 15:00–17:00; availability 10:00–11:00, 12:00–12:30, 15:00–17:00.",
        f"  Sunday {week + timedelta(days=6)}: recurring 22:00–06:00 plus one-time 23:00–02:00; inspect both weeks.",
        f"  Working windows/overrides: {root}/working-windows/?date={week}",
        f"  Recurring edit/end/history: {root}/recurring/", f"  One-time edit/delete: {root}/commitments/",
        f"  Future rules: {root}/week/?week={change} (Job A 10:00–14:00; Job B 17:00–21:00).",
        f"  Future moved exception: {change + timedelta(days=2)} 14:00–16:00, preserved through the rule change.",
        f"  Closed carry-in Monday: {change + timedelta(days=7)}; Job A ends before {change + timedelta(days=14)}.",
        "", f"SHIFT CHECKS: {root}/check-shift/?date={week}",
        f"  {week} 08:00–10:00: available (class starts exactly at 10:00).",
        f"  {week} 10:30–11:30: commitment conflict, inside working windows.",
        f"  {week} 07:00–09:00: outside working windows 07:00–08:00, no commitment conflict.",
        f"  {week} 07:00–11:00: both outside working windows and a commitment conflict.",
        "  Submit each offer; checking saves nothing. Add an overlapping commitment to test save warnings.",
        "", "OTHER ACCOUNTS (sign out before switching):",
        f"  schedule_demo_other: {root}/availability/?week={week}; private Monday 09:00–10:00 must not affect main account.",
        f"  Its Friday {week + timedelta(days=4)} has working windows but no availability (fully occupied).",
        "  schedule_demo_empty: /commitments/, /recurring/, /working-windows/, /availability/ for first-use/empty states.",
        "", "CLOCK CHANGES: schedule_demo_dst",
        f"  Spring: {root}/week/?week={plan.spring}; 02:15 becomes 03:15; invalid 02:30–03:00 needs review.",
        f"  Draft availability/copy: {root}/availability/?week={plan.spring}",
        f"  Review working hours: {root}/working-windows/?date={plan.spring}",
        "  Fix the working date AND the invalid commitment (change/cancel its occurrence), then reload availability.",
        f"  Fall: {root}/week/?week={plan.fall}; first 01:15 ADT through second 01:45 AST.",
        f"  Repeated-hour choices: {root}/check-shift/?date={plan.fall}",
        "  Check 01:45 to 01:15 with second end selected: positive 30-minute shift, with commitment conflicts.",
        "", "Reruns preserve manual edits and the original demo week; --reset restores only these demo accounts.",
        "Use --reset --week YYYY-MM-DD to move the demo. See docs/demo_data.md for the complete manual checklist.",
    ]
    return "\n".join(lines)
