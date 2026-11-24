from datetime import UTC, date, datetime, time, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command, CommandError
from django.urls import reverse
from django.utils import timezone

from scheduling.availability import check_proposed_shift, weekly_availability_for_user
from scheduling.availability_presentation import availability_screen_for_user
from scheduling.demo_data import DEMO_ACCOUNTS, DEMO_MARKER, DEMO_PASSWORD, demo_walkthrough, seed_demo
from scheduling.intervals import date_bounds
from scheduling.models import Commitment, CommitmentSource, WorkingDateOverride, WorkingScheduleRevision
from scheduling.recurrence import occurrences_for_user
from scheduling.services import commitments_for_user, save_commitment
from scheduling.working_windows import WindowSpec, set_working_schedule, working_windows_for_user


pytestmark = pytest.mark.django_db
WEEK = date(2026, 11, 16)
ZONE = ZoneInfo("America/Halifax")


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 11, 18, 15, tzinfo=UTC))


@pytest.fixture
def seeded():
    return seed_demo()


def user(username="schedule_demo"):
    return get_user_model().objects.get(username=username)


def instant(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), ZONE)


def intervals(day):
    return [(item.starts_at.astimezone(ZONE).strftime("%H:%M"), item.ends_at.astimezone(ZONE).strftime("%H:%M"))
            for item in day.intervals]


def occurrence_read(owner, day):
    lower, _ = date_bounds(day, ZONE.key)
    _, upper = date_bounds(day + timedelta(days=6), ZONE.key)
    return occurrences_for_user(owner=owner, starts_at=lower, ends_at=upper)


def snapshot():
    return {model._meta.label: list(model.objects.order_by("pk").values()) for model in apps.get_models()}


def test_command_creates_four_nonprivileged_accounts_and_prints_actual_journey():
    output = StringIO()
    call_command("seed_demo", stdout=output)
    assert get_user_model().objects.count() == 4
    for username in DEMO_ACCOUNTS:
        account = user(username)
        assert account.check_password(DEMO_PASSWORD)
        assert account.is_active and not account.is_staff and not account.is_superuser
        assert not account.get_all_permissions()
        assert account.groups.filter(name=DEMO_MARKER).exists()
    text = output.getvalue()
    assert "2026-11-16 through 2026-11-22" in text
    assert "future changes: 2026-11-23" in text
    for path in ("/week/?week=2026-11-16", "/availability/?week=2026-11-16", "/check-shift/?date=2026-11-16",
                 "/working-windows/?date=2026-11-16", "/recurring/", "/commitments/"):
        assert path in text
    assert DEMO_PASSWORD in text


def test_main_acceptance_monday_has_exact_hours_without_other_account_details(seeded):
    result = availability_screen_for_user(owner=user(), anchor=WEEK)
    assert [(slot.start_label, slot.end_label) for slot in result["days"][0].slots] == [("08:00", "10:00"), ("14:00", "20:00")]
    assert "Demo ·" not in result["share_text"]
    assert "schedule_demo" not in result["share_text"]
    assert "Private other-account" not in result["share_text"]


def test_seeded_conflict_and_archived_obligations_remain_visible(seeded):
    owner = user()
    rows = commitments_for_user(owner=owner)
    training = next(item for item in rows if item.title == "Demo · Conflicting training")
    assert training.has_conflict
    retired = CommitmentSource.objects.get(owner=owner, name__contains="Former employer")
    assert retired.archived_at
    weekly = weekly_availability_for_user(owner=owner, anchor=WEEK)
    assert intervals(weekly.days[5]) == [("10:00", "11:00"), ("12:00", "12:30"), ("15:00", "17:00")]
    assert intervals(weekly.days[3]) == []
    assert retired.commitments.count() == retired.recurring_series.count() == 1


def test_recurrence_move_cancel_future_history_and_ending_match_report(seeded):
    owner = user()
    current = occurrence_read(owner, WEEK).occurrences
    assert not any(item.title == "Demo · Protected personal time" for item in current)
    moved = [item for item in current if item.title == "Demo · Moved Job A shift"]
    assert len(moved) == 1 and moved[0].starts_at.astimezone(ZONE) == instant(WEEK + timedelta(days=2), 14)
    future = occurrence_read(owner, seeded.plan.changes_on).occurrences
    assert any(item.title == "Demo · Job A revised hours" for item in future)
    assert any(item.title == "Demo · Job B revised hours" for item in future)
    assert any(item.is_replacement and item.original_start_date == seeded.plan.changes_on + timedelta(days=1) for item in future)
    assert any(item.title == "Demo · Job A shift" for item in occurrence_read(owner, WEEK).occurrences)
    ended = occurrence_read(owner, seeded.plan.changes_on + timedelta(days=14)).occurrences
    assert not any("Job A" in item.title for item in ended)


def test_both_overnight_types_cross_week_boundary_and_final_occurrence_is_full(seeded):
    owner = user()
    week_start, _ = date_bounds(WEEK, ZONE.key)
    week_end, _ = date_bounds(WEEK + timedelta(days=7), ZONE.key)
    first_week = occurrences_for_user(owner=owner, starts_at=week_start, ends_at=week_end)
    nights = [item for item in first_week.occurrences if item.title == "Demo · Sunday overnight"]
    assert len(nights) == 2
    assert nights[0].starts_at < week_start < nights[0].ends_at
    assert nights[1].ends_at.astimezone(ZONE) == instant(WEEK + timedelta(days=7), 6)
    overnight = Commitment.objects.get(source__owner=owner, title="Demo · One-time overnight")
    assert overnight.starts_at < week_end < overnight.ends_at
    later = weekly_availability_for_user(owner=owner, anchor=WEEK + timedelta(days=7))
    assert all(item.starts_at >= instant(WEEK + timedelta(days=7), 6) for item in later.days[0].intervals)


def test_future_working_revision_and_full_date_override_preserve_history(seeded):
    owner = user()
    current = WorkingScheduleRevision.objects.get(owner=owner, effective_from__lte=WEEK, effective_until__gt=WEEK)
    later = WorkingScheduleRevision.objects.get(owner=owner, effective_from=seeded.plan.changes_on)
    assert current.windows.get(weekday=0).start_time == time(8)
    assert later.windows.get(weekday=0).start_time == time(9)
    closed_day = seeded.plan.changes_on + timedelta(days=7)
    lower, upper = date_bounds(closed_day, ZONE.key)
    assert not working_windows_for_user(owner=owner, starts_at=lower, ends_at=upper).intervals
    assert WorkingDateOverride.objects.get(owner=owner, local_date=closed_day).intervals.count() == 0


@pytest.mark.parametrize("start,end,available,conflict,outside", [
    (8, 10, True, False, False), (10.5, 11.5, False, True, False),
    (7, 9, False, False, True), (7, 11, False, True, True),
])
def test_seeded_shift_examples_have_advertised_results(seeded, start, end, available, conflict, outside):
    lower = instant(WEEK, int(start), int(start % 1 * 60))
    upper = instant(WEEK, int(end), int(end % 1 * 60))
    result = check_proposed_shift(owner=user(), starts_at=lower, ends_at=upper)
    assert result.is_available is available
    assert bool(result.conflicts) is conflict
    assert bool(result.outside_working_windows) is outside


def test_other_account_has_private_shift_and_fully_occupied_day(seeded):
    other = user("schedule_demo_other")
    result = weekly_availability_for_user(owner=other, anchor=WEEK)
    assert intervals(result.days[0]) == [("08:00", "09:00"), ("10:00", "17:00")]
    assert not result.days[4].intervals
    assert result.result.working_windows
    assert Commitment.objects.filter(source__owner=other).count() == 2


def test_empty_account_has_no_sources_rules_commitments_or_availability(seeded, client):
    empty = user("schedule_demo_empty")
    assert not empty.commitment_sources.exists()
    assert not WorkingScheduleRevision.objects.filter(owner=empty).exists()
    result = weekly_availability_for_user(owner=empty, anchor=WEEK)
    assert result.complete and not result.result.available
    client.force_login(empty)
    for route in ("commitment_list", "series_list", "working_windows", "availability", "shift_check"):
        assert client.get(reverse(f"scheduling:{route}")).status_code == 200


def test_dst_account_produces_clock_notes_and_draft_review_without_affecting_main(seeded):
    owner = user("schedule_demo_dst")
    spring = seeded.plan.spring
    result = availability_screen_for_user(owner=owner, anchor=spring)
    assert not result["complete"] and "Draft:" in result["share_text"]
    assert not result["days"][6].complete
    recurring = occurrence_read(owner, spring - timedelta(days=6))
    assert recurring.issues
    shifted = next(item for item in recurring.occurrences if item.title == "Demo · Spring shifted time")
    assert shifted.start_resolution.adjustment == "gap_shift_forward"
    assert shifted.starts_at.astimezone(ZONE).hour == 3
    assert weekly_availability_for_user(owner=user(), anchor=WEEK).complete
    fall = occurrence_read(owner, seeded.plan.fall - timedelta(days=6))
    assert any(item.start_resolution.adjustment == "fold_first" for item in fall.occurrences)
    both = Commitment.objects.get(source__owner=owner, title="Demo · Both repeated hours")
    assert both.ends_at - both.starts_at == timedelta(minutes=90)


def test_all_seed_accounts_can_log_in_and_privacy_survives_direct_urls(seeded, client):
    foreign = Commitment.objects.get(source__owner=user("schedule_demo_other"), title__contains="Private")
    for username in DEMO_ACCOUNTS:
        assert client.login(username=username, password=DEMO_PASSWORD)
        assert client.get(reverse("scheduling:week"), {"week": WEEK.isoformat()}).status_code == 200
        client.logout()
    assert client.login(username="schedule_demo", password=DEMO_PASSWORD)
    assert client.get(reverse("scheduling:commitment_update", args=[foreign.pk])).status_code == 404
    assert b"Private other-account shift" not in client.get(reverse("scheduling:commitment_list")).content


def test_rerun_is_idempotent_and_preserves_manual_edits_passwords_and_original_week(seeded, monkeypatch):
    empty = user("schedule_demo_empty")
    source = CommitmentSource.objects.create(owner=empty, name="My manual source")
    save_commitment(owner=empty, commitment=Commitment(source=source, title="My manual test",
                    starts_at=instant(WEEK, 8), ends_at=instant(WEEK, 9)))
    empty.set_password("MyChangedPassword!2026")
    empty.save()
    before = snapshot()
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 12, 18, 15, tzinfo=UTC))
    repeated = seed_demo()
    assert snapshot() == before
    assert repeated.plan == seeded.plan
    assert repeated.unchanged == tuple(DEMO_ACCOUNTS)
    assert not repeated.created and not repeated.restored


def test_reset_restores_only_demo_graph_and_preserves_real_data(seeded, owner, source):
    real = Commitment.objects.create(source=source, title="Real schedule",
                                     starts_at=instant(WEEK, 8), ends_at=instant(WEEK, 9))
    empty = user("schedule_demo_empty")
    manual_source = CommitmentSource.objects.create(owner=empty, name="Temporary edits")
    Commitment.objects.create(source=manual_source, title="Temporary", starts_at=instant(WEEK, 8), ends_at=instant(WEEK, 9))
    empty.set_password("Changed!2026")
    empty.is_staff = True
    empty.save()
    set_working_schedule(owner=empty, effective_from=WEEK, windows=[WindowSpec(0, time(8), time(20))])
    restored = seed_demo(reset=True)
    assert restored.restored == tuple(DEMO_ACCOUNTS)
    assert Commitment.objects.get(pk=real.pk).title == "Real schedule"
    assert source.owner_id == owner.pk and get_user_model().objects.filter(pk=owner.pk).exists()
    assert not CommitmentSource.objects.filter(owner=empty).exists()
    assert not WorkingScheduleRevision.objects.filter(owner=empty).exists()
    assert user("schedule_demo_empty").check_password(DEMO_PASSWORD)
    assert not user("schedule_demo_empty").is_staff
    assert availability_screen_for_user(owner=user(), anchor=WEEK)["days"][0].slots[0].start_label == "08:00"
    assert Group.objects.filter(name__startswith=f"{DEMO_MARKER}:").count() == 1


@pytest.mark.parametrize("reset", [False, True])
def test_real_username_collision_never_takes_over_or_deletes_data(reset):
    existing = get_user_model().objects.create_user(username="schedule_demo_other", password="Real!2026")
    source = CommitmentSource.objects.create(owner=existing, name="Real source")
    before = snapshot()
    with pytest.raises(CommandError, match="not seed-owned"):
        call_command("seed_demo", reset=reset, stdout=StringIO())
    assert snapshot() == before
    assert source.owner_id == existing.pk


def test_different_week_requires_explicit_reset_then_moves_every_demo(seeded):
    before = snapshot()
    with pytest.raises(CommandError, match="Use --reset"):
        call_command("seed_demo", week="2026-12-02", stdout=StringIO())
    assert snapshot() == before
    output = StringIO()
    call_command("seed_demo", week="2026-12-02", reset=True, stdout=output)
    assert "Demo week: 2026-11-30" in output.getvalue()
    assert "future changes: 2026-12-07" in output.getvalue()
    commitment = Commitment.objects.get(source__owner=user(), title="Demo · Protected study")
    assert commitment.starts_at.astimezone(ZONE).date() == date(2026, 11, 30)


@pytest.mark.parametrize("value", ["", "20261116", "2026-02-30", "2006-01-02", "2100-01-04"])
def test_bad_week_fails_before_persisting_anything(value):
    before = snapshot()
    with pytest.raises(CommandError):
        call_command("seed_demo", week=value, stdout=StringIO())
    assert snapshot() == before


def test_partial_seed_failure_rolls_back_all_accounts_and_reset_changes(seeded, monkeypatch):
    before = snapshot()
    def broken(*args):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr("scheduling.demo_data._dst_schedule", broken)
    with pytest.raises(RuntimeError, match="fixture failure"):
        seed_demo(reset=True)
    assert snapshot() == before


def test_historical_anchor_keeps_future_operations_in_the_future():
    result = seed_demo(week="2026-03-04")
    assert result.plan.week == date(2026, 3, 2)
    assert result.plan.changes_on == date(2026, 11, 23)
    assert f"future changes: {result.plan.changes_on}" in demo_walkthrough(result)
    assert not weekly_availability_for_user(owner=user("schedule_demo_dst"), anchor=result.plan.spring).complete


def test_active_timezone_does_not_change_default_demo_week():
    with timezone.override("Pacific/Auckland"):
        result = seed_demo()
    assert result.plan.week == WEEK


def test_missing_demo_account_can_be_recreated_without_changing_existing_accounts(seeded):
    user("schedule_demo_empty").delete()
    main = user()
    before = list(Commitment.objects.filter(source__owner=main).values())
    result = seed_demo()
    assert result.created == ("schedule_demo_empty",)
    assert list(Commitment.objects.filter(source__owner=main).values()) == before
