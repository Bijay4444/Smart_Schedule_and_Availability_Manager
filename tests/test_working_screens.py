from datetime import UTC, date, datetime, time

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from scheduling.availability import availability_for_user
from scheduling.models import OverrideInterval, WorkingDateOverride, WorkingScheduleRevision, WorkingWindow
from scheduling.working_windows import (
    WindowSpec, resolve_override_interval, set_working_date_override, set_working_schedule,
    working_schedule_initial, working_window_screen,
)


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("scheduling.working_windows.timezone.now", lambda: datetime(2026, 10, 26, 15, tzinfo=UTC))


def rowset(prefix, rows, initial=0):
    result = {f"{prefix}-TOTAL_FORMS": str(len(rows)), f"{prefix}-INITIAL_FORMS": str(initial),
              f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "100"}
    for index, row in enumerate(rows):
        result.update({f"{prefix}-{index}-{key}": value for key, value in row.items()})
    return result


def weekly_data(rows=None, **changes):
    return {"effective_from": "2026-10-26", **rowset("windows", rows if rows is not None else [
        {"weekday": "0", "start_time": "08:00", "end_time": "12:00"},
        {"weekday": "0", "start_time": "14:00", "end_time": "20:00"},
        {"weekday": "6", "start_time": "22:00", "end_time": "06:00", "ends_next_day": "on"},
    ]), **changes}


def override_data(rows=None, **changes):
    return {"local_date": "2026-10-26", **rowset("intervals", rows if rows is not None else [
        {"start_time": "09:00", "end_time": "12:00"},
        {"start_time": "14:00", "end_time": "18:00"},
    ]), **changes}


def post(client, owner, route, data, args=None, **kwargs):
    client.force_login(owner)
    return client.post(reverse(f"scheduling:{route}", args=args), data, **kwargs)


@pytest.fixture
def override(owner):
    return set_working_date_override(owner=owner, local_date=MONDAY, intervals=[])


@pytest.mark.parametrize("route", ["working_windows", "working_schedule_edit", "working_override_create", "working_override_edit", "working_override_remove"])
def test_working_screens_require_login(client, override, route):
    args = [override.pk] if route in ("working_override_edit", "working_override_remove") else []
    response = client.get(reverse(f"scheduling:{route}", args=args))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_empty_screen_explains_windows_and_contains_no_work_availability_claim(client, owner):
    client.force_login(owner)
    response = client.get(reverse("scheduling:working_windows"))
    assert response.status_code == 200
    assert b"No weekly pattern is configured" in response.content
    assert b"before commitments are subtracted" in response.content
    assert b"No date overrides" in response.content
    assert b"Set weekly windows" in response.content


def test_save_multiple_windows_per_weekday_and_overnight_hours(client, owner):
    response = post(client, owner, "working_schedule_edit", weekly_data(), follow=True)
    assert response.status_code == 200
    assert WorkingScheduleRevision.objects.count() == 1
    assert WorkingWindow.objects.count() == 3
    assert b"08:00" in response.content and b"14:00" in response.content
    assert b"next day" in response.content
    assert b"Sunday" in response.content


def test_edit_is_prefilled_from_selected_effective_date_and_preserves_history(client, owner):
    first = set_working_schedule(owner=owner, effective_from=MONDAY, windows=[WindowSpec(0, time(8), time(12))])
    client.force_login(owner)
    response = client.get(reverse("scheduling:working_schedule_edit"), {"date": "2026-11-16"})
    assert response.context["rows"].initial[0]["start_time"] == time(8)
    response = post(client, owner, "working_schedule_edit", weekly_data(
        rows=[{"weekday": "0", "start_time": "10:00", "end_time": "16:00"}], effective_from="2026-11-16"))
    assert response.status_code == 302
    first.refresh_from_db()
    assert first.effective_until == date(2026, 11, 16)
    assert first.windows.get().start_time == time(8)
    assert working_schedule_initial(owner=owner, effective_from=MONDAY)[0]["start_time"] == time(8)


def test_future_patterns_are_superseded_and_explicit_date_overrides_survive(client, owner, override):
    set_working_schedule(owner=owner, effective_from=MONDAY, windows=[WindowSpec(0, time(8), time(12))])
    set_working_schedule(owner=owner, effective_from=date(2026, 12, 7), windows=[WindowSpec(0, time(14), time(20))])
    response = post(client, owner, "working_schedule_edit", weekly_data(effective_from="2026-11-16"))
    assert response.status_code == 302
    assert WorkingScheduleRevision.objects.count() == 2
    assert not WorkingScheduleRevision.objects.filter(effective_from=date(2026, 12, 7)).exists()
    assert WorkingDateOverride.objects.filter(pk=override.pk).exists()


def test_past_initial_setup_is_allowed_but_subsequent_past_rewrite_is_rejected(client, owner):
    response = post(client, owner, "working_schedule_edit", weekly_data(effective_from="2026-10-01"))
    assert response.status_code == 302
    response = post(client, owner, "working_schedule_edit", weekly_data(effective_from="2026-10-19"))
    assert response.status_code == 200
    assert b"preserve earlier schedules" in response.content
    assert WorkingScheduleRevision.objects.count() == 1


@pytest.mark.parametrize("rows", [
    [{"weekday": "0", "start_time": "12:00", "end_time": "08:00"}],
    [{"weekday": "7", "start_time": "08:00", "end_time": "12:00"}],
    [{"weekday": "0", "start_time": "08:00", "end_time": "12:00"}] * 2,
])
def test_invalid_windows_do_not_write_a_schedule(client, owner, rows):
    response = post(client, owner, "working_schedule_edit", weekly_data(rows=rows))
    assert response.status_code == 200
    assert not WorkingScheduleRevision.objects.exists()


def test_empty_weekly_pattern_requires_explicit_no_windows_choice(client, owner):
    response = post(client, owner, "working_schedule_edit", weekly_data(rows=[]))
    assert response.status_code == 200
    assert not WorkingScheduleRevision.objects.exists()
    response = post(client, owner, "working_schedule_edit", weekly_data(rows=[], no_windows="on"))
    assert response.status_code == 302
    assert WorkingScheduleRevision.objects.count() == 1
    assert not WorkingWindow.objects.exists()


def test_empty_choice_cannot_silently_discard_entered_windows(client, owner):
    response = post(client, owner, "working_schedule_edit", weekly_data(no_windows="on"))
    assert response.status_code == 200
    assert not WorkingScheduleRevision.objects.exists()


def test_explicit_empty_weekly_schedule_is_prefilled_as_empty(client, owner):
    set_working_schedule(owner=owner, effective_from=MONDAY, windows=[])
    client.force_login(owner)
    response = client.get(reverse("scheduling:working_schedule_edit"))
    assert response.context["form"]["no_windows"].value() is True


def test_rows_marked_for_removal_are_not_saved(client, owner):
    response = post(client, owner, "working_schedule_edit", weekly_data(rows=[
        {"weekday": "0", "start_time": "08:00", "end_time": "12:00"},
        {"weekday": "0", "start_time": "14:00", "end_time": "20:00", "DELETE": "on"},
    ]))
    assert response.status_code == 302
    assert WorkingWindow.objects.count() == 1


@pytest.mark.parametrize("route,data,prefix", [
    ("working_schedule_edit", weekly_data(), "windows"),
    ("working_override_create", override_data(), "intervals"),
])
def test_add_row_works_without_javascript_and_does_not_save(client, owner, route, data, prefix):
    response = post(client, owner, route, {**data, "action": "add_window"})
    assert response.status_code == 200
    assert response.context["rows"].total_form_count() == int(data[f"{prefix}-TOTAL_FORMS"]) + 1
    assert response.context["rows"].forms[0]["start_time"].value() in ("08:00", "09:00")
    assert not WorkingScheduleRevision.objects.exists()
    assert not WorkingDateOverride.objects.exists()


@pytest.mark.parametrize("changes", [{"windows-TOTAL_FORMS": "100000"}, {"windows-TOTAL_FORMS": "broken"},
                                     {"windows-TOTAL_FORMS": "-1"}])
def test_malformed_management_data_does_not_write(client, owner, changes):
    response = post(client, owner, "working_schedule_edit", weekly_data(**changes))
    assert response.status_code == 200
    assert not WorkingScheduleRevision.objects.exists()


def test_omitted_management_form_is_a_recoverable_error(client, owner):
    response = post(client, owner, "working_schedule_edit", {"effective_from": "2026-10-26"})
    assert response.status_code == 200
    assert response.context["rows"].non_form_errors()
    assert not WorkingScheduleRevision.objects.exists()


def test_date_override_supports_multiple_intervals_and_stable_edit_identity(client, owner):
    response = post(client, owner, "working_override_create", override_data())
    assert response.status_code == 302
    override = WorkingDateOverride.objects.get()
    assert override.intervals.count() == 2
    client.force_login(owner)
    response = client.get(reverse("scheduling:working_override_edit", args=[override.pk]))
    assert response.context["rows"].initial[0]["start_time"] == time(9)
    # A forged new date is ignored by the disabled field on the owned edit route.
    response = post(client, owner, "working_override_edit", override_data(rows=[
        {"start_time": "11:00", "end_time": "18:00"},
    ], local_date="2026-11-01"), args=[override.pk])
    assert response.status_code == 302
    override.refresh_from_db()
    assert override.local_date == MONDAY
    assert WorkingDateOverride.objects.count() == 1
    assert override.intervals.count() == 1


def test_closed_date_replaces_overnight_carry_in_and_can_restore_weekly_windows(client, owner, halifax_time):
    set_working_schedule(owner=owner, effective_from=date(2026, 10, 19), windows=[WindowSpec(6, time(22), time(6), 1)])
    response = post(client, owner, "working_override_create", override_data(rows=[], closed_all_day="on"), follow=True)
    assert response.status_code == 200
    assert b"Unavailable for work all day" in response.content
    bounds = {"owner": owner, "starts_at": halifax_time("2026-10-26T00:00"), "ends_at": halifax_time("2026-10-27T00:00")}
    assert availability_for_user(**bounds).available == ()
    override = WorkingDateOverride.objects.get()
    url = reverse("scheduling:working_override_remove", args=[override.pk])
    assert client.get(url).status_code == 200
    assert WorkingDateOverride.objects.count() == 1
    assert client.post(url, {}).status_code == 200
    assert WorkingDateOverride.objects.count() == 1
    assert client.post(url, {"confirm": "on"}).status_code == 302
    assert not WorkingDateOverride.objects.exists()
    assert availability_for_user(**bounds).available[0].ends_at == halifax_time("2026-10-26T06:00")


def test_blank_override_requires_explicit_closed_all_day_choice(client, owner):
    response = post(client, owner, "working_override_create", override_data(rows=[]))
    assert response.status_code == 200
    assert not WorkingDateOverride.objects.exists()
    response = post(client, owner, "working_override_create", override_data(closed_all_day="on"))
    assert response.status_code == 200
    assert not WorkingDateOverride.objects.exists()


@pytest.mark.parametrize("day,hours", [("2026-03-08", 23), ("2026-11-01", 25)])
def test_full_day_override_uses_following_midnight_across_dst(client, owner, day, hours):
    response = post(client, owner, "working_override_create", override_data(rows=[
        {"start_time": "00:00", "end_at_midnight": "on"},
    ], local_date=day))
    assert response.status_code == 302
    interval = OverrideInterval.objects.get()
    assert (interval.ends_at - interval.starts_at).total_seconds() == hours * 3600


def test_missing_clock_time_is_shifted_and_explained_after_saving(client, owner):
    response = post(client, owner, "working_override_create", override_data(rows=[
        {"start_time": "02:15", "end_time": "04:00"},
    ], local_date="2026-03-08"), follow=True)
    assert response.status_code == 200
    assert b"moved forward for the clock change" in response.content
    assert b"03:15 ADT" in response.content
    assert WorkingDateOverride.objects.count() == 1


def test_invalid_resolved_override_is_not_saved_and_existing_intervals_survive(client, owner, override):
    response = post(client, owner, "working_override_create", override_data(rows=[
        {"start_time": "02:30", "end_time": "03:00"},
    ], local_date="2026-03-08"))
    assert response.status_code == 200
    assert b"End must follow start after the clock-change choices" in response.content
    assert WorkingDateOverride.objects.count() == 1
    assert WorkingDateOverride.objects.get().pk == override.pk


def test_second_repeated_hour_round_trips_through_edit_form(client, owner):
    response = post(client, owner, "working_override_create", override_data(rows=[
        {"start_time": "01:15", "end_time": "01:45", "second_start": "on", "second_end": "on"},
    ], local_date="2026-11-01"))
    assert response.status_code == 302
    override = WorkingDateOverride.objects.get()
    response = client.get(reverse("scheduling:working_override_edit", args=[override.pk]))
    initial = response.context["rows"].initial[0]
    assert initial["second_start"] and initial["second_end"]
    before = tuple(override.intervals.values_list("starts_at", "ends_at"))
    response = post(client, owner, "working_override_edit", override_data(rows=[
        {"start_time": "01:15", "end_time": "01:45", "second_start": "on", "second_end": "on"},
    ]), args=[override.pk])
    assert response.status_code == 302
    assert tuple(override.intervals.values_list("starts_at", "ends_at")) == before


@pytest.mark.parametrize("changes", [{"second_start": True}, {"second_end": True},
                                     {"end_at_midnight": True}, {"start_time": time(20), "end_time": time(8)}])
def test_override_clock_choices_are_validated(changes):
    with pytest.raises(ValidationError):
        resolve_override_interval(**{"local_date": MONDAY, "start_time": time(8), "end_time": time(12), **changes})


def test_working_preview_exposes_invalid_date_with_correction_link(client, owner):
    set_working_schedule(owner=owner, effective_from=date(2026, 3, 8), windows=[WindowSpec(6, time(2, 30), time(3))])
    client.force_login(owner)
    response = client.get(reverse("scheduling:working_windows"), {"date": "2026-03-08"})
    assert response.status_code == 200
    assert b"Working hours need review" in response.content
    assert b"Correct this date" in response.content
    assert response.context["screen"]["days"][6]["intervals"] == ()


@pytest.mark.parametrize("route", ["working_override_edit", "working_override_remove"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_other_users_override_routes_are_not_accessible(client, owner, other_owner, override, route, method):
    client.force_login(other_owner)
    response = getattr(client, method)(reverse(f"scheduling:{route}", args=[override.pk]), override_data())
    assert response.status_code == 404
    assert WorkingDateOverride.objects.filter(pk=override.pk).exists()


def test_overview_initial_values_and_writes_remain_private(client, owner, other_owner):
    set_working_schedule(owner=other_owner, effective_from=MONDAY, windows=[WindowSpec(0, time(3, 17), time(5, 23))])
    set_working_date_override(owner=other_owner, local_date=MONDAY, intervals=[])
    client.force_login(owner)
    response = client.get(reverse("scheduling:working_windows"))
    assert response.status_code == 200
    assert b"03:17" not in response.content
    assert b"Unavailable for work all day" not in response.content
    assert working_schedule_initial(owner=owner, effective_from=MONDAY) == []
    response = post(client, owner, "working_schedule_edit", {**weekly_data(), "owner": other_owner.pk})
    assert response.status_code == 302
    assert WorkingScheduleRevision.objects.filter(owner=owner).count() == 1
    assert WorkingScheduleRevision.objects.filter(owner=other_owner).count() == 1


@pytest.mark.parametrize("route", ["working_schedule_edit", "working_override_create", "working_override_edit", "working_override_remove"])
def test_window_writes_require_csrf(owner, override, route):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    args = [override.pk] if route in ("working_override_edit", "working_override_remove") else []
    response = client.post(reverse(f"scheduling:{route}", args=args), weekly_data())
    assert response.status_code == 403
    assert WorkingDateOverride.objects.filter(pk=override.pk).exists()


@pytest.mark.parametrize("route", ["working_windows", "working_schedule_edit", "working_override_create"])
def test_invalid_query_dates_are_handled_without_server_error(client, owner, route):
    client.force_login(owner)
    assert client.get(reverse(f"scheduling:{route}"), {"date": "invalid"}).status_code == 400


def test_return_location_cannot_be_forged(client, owner):
    client.force_login(owner)
    response = client.post(reverse("scheduling:working_schedule_edit") + "?next=https://example.com", weekly_data())
    assert response.url.startswith(reverse("scheduling:working_windows"))


def test_working_screen_query_count_stays_bounded(owner, django_assert_max_num_queries):
    set_working_schedule(owner=owner, effective_from=MONDAY,
                         windows=[WindowSpec(day, time(hour), time(hour + 1)) for day in range(7) for hour in (8, 10, 14)])
    for day in range(26, 31):
        set_working_date_override(owner=owner, local_date=date(2026, 10, day), intervals=[])
    with django_assert_max_num_queries(8):
        screen = working_window_screen(owner=owner, anchor=MONDAY)
        assert len(screen["days"]) == 7
        assert len(list(screen["overrides"])) == 5
