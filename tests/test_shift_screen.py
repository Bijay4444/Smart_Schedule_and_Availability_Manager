from datetime import UTC, date, time

import pytest
from django.apps import apps
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from scheduling.models import Commitment
from scheduling.recurrence import cancel_occurrence, create_series, reschedule_occurrence
from scheduling.services import archive_source
from scheduling.shift_presentation import shift_screen_for_user
from scheduling.working_windows import WindowSpec, set_working_date_override, set_working_schedule


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 10, 26)


def window(owner, *windows, effective_from=MONDAY):
    return set_working_schedule(owner=owner, effective_from=effective_from, windows=windows)


def submit(client, starts="2026-10-26T09:00", ends="2026-10-26T10:00", **extra):
    return client.post(reverse("scheduling:shift_check"), {"starts_at": starts, "ends_at": ends, **extra})


def rule(owner, source, **extra):
    values = dict(source_id=source.pk, title="Private class", starts_on=MONDAY,
                  weekdays=[0], start_time=time(10), end_time=time(12))
    return create_series(owner=owner, **(values | extra))


@pytest.mark.parametrize("method", ["get", "post"])
def test_shift_check_requires_login(client, method):
    response = getattr(client, method)(reverse("scheduling:shift_check"))
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/?next=")


def test_get_has_no_result_and_is_private_and_linked_from_availability(client, owner):
    client.force_login(owner)
    response = client.get(reverse("scheduling:shift_check"))
    assert response.status_code == 200
    assert "result" not in response.context
    assert response["Cache-Control"] == "private, no-store"
    assert b'action="/check-shift/#shift-result-heading"' in response.content
    assert b'aria-current="page"><svg' in response.content
    availability = client.get(reverse("scheduling:availability"), {"week": "2026-10-26"})
    assert b'/check-shift/?date=2026-10-26' in availability.content


def test_selected_date_prefills_local_input_without_calculating(client, owner):
    client.force_login(owner)
    response = client.get(reverse("scheduling:shift_check"), {"date": "2026-10-28"})
    assert response.context["form"]["starts_at"].value() == "2026-10-28T09:00"
    assert response.context["form"]["ends_at"].value() == "2026-10-28T17:00"
    assert "result" not in response.context


@pytest.mark.parametrize("day", ["", "20261026", "2026-02-30", "0001-01-01", "9999-12-31"])
def test_invalid_date_link_is_bad_request(client, owner, day):
    client.force_login(owner)
    assert client.get(reverse("scheduling:shift_check"), {"date": day}).status_code == 400


def test_entire_shift_inside_windows_is_available_and_read_only(client, owner, source):
    window(owner, WindowSpec(0, time(8), time(20)))
    rule(owner, source)
    client.force_login(owner)
    # Checking is a read across all installed model tables, including sessions.
    before = {model: list(model.objects.order_by("pk").values()) for model in apps.get_models()}
    response = submit(client)
    assert response.context["result"]["available"]
    assert b"Available for this shift" in response.content
    assert b"Nothing was saved" in response.content
    assert response["Cache-Control"] == "private, no-store"
    assert {model: list(model.objects.order_by("pk").values()) for model in apps.get_models()} == before


def test_no_windows_reports_outside_hours_instead_of_free_time(client, owner):
    client.force_login(owner)
    response = submit(client)
    result = response.context["result"]
    assert result["complete"] and not result["available"]
    assert len(result["outside"]) == 1
    assert not result["conflicts"]
    assert b"Not available for the full shift" in response.content


def test_separate_conflicts_and_outside_hours_and_escape_private_titles(client, owner, source, commitment):
    window(owner, WindowSpec(0, time(8), time(11)))
    commitment.title = '<script>alert("private")</script>'
    commitment.save()
    rule(owner, source)
    client.force_login(owner)
    response = submit(client, "2026-10-26T10:30", "2026-10-26T13:00")
    result = response.context["result"]
    assert len(result["conflicts"]) == 2
    assert result["outside"][0]["starts_at"].hour == 11
    assert result["outside"][0]["ends_at"].hour == 13
    assert b"Commitment conflicts" in response.content and b"Outside working windows" in response.content
    assert b"<script>" not in response.content
    assert b"&lt;script&gt;" in response.content
    assert b"/week/?week=2026-10-26" in response.content


def test_split_working_windows_keep_each_uncovered_gap(client, owner):
    window(owner, WindowSpec(0, time(8), time(10)), WindowSpec(0, time(12), time(14)))
    client.force_login(owner)
    result = submit(client, "2026-10-26T07:00", "2026-10-26T15:00").context["result"]
    assert [(item["starts_at"].hour, item["ends_at"].hour) for item in result["outside"]] == [(7, 8), (10, 12), (14, 15)]


@pytest.mark.parametrize("starts,ends", [("08:00", "10:00"), ("12:00", "14:00")])
def test_touching_commitment_boundaries_are_available(client, owner, commitment, starts, ends):
    window(owner, WindowSpec(0, time(8), time(20)))
    client.force_login(owner)
    assert submit(client, f"2026-10-26T{starts}", f"2026-10-26T{ends}").context["result"]["available"]


def test_overnight_week_boundary_checks_both_dates_and_empty_override(client, owner):
    window(owner, WindowSpec(6, time(22), time(6), 1), effective_from=date(2026, 10, 25))
    client.force_login(owner)
    assert submit(client, "2026-10-25T23:00", "2026-10-26T05:00").context["result"]["available"]
    set_working_date_override(owner=owner, local_date=MONDAY, intervals=[])
    result = submit(client, "2026-10-25T23:00", "2026-10-26T05:00").context["result"]
    assert not result["available"]
    assert result["outside"][0]["starts_at"].isoformat() == "2026-10-26T00:00:00-03:00"


def test_archived_recurring_sources_keep_blocking_shift(client, owner, source):
    window(owner, WindowSpec(0, time(8), time(20)))
    rule(owner, source)
    archive_source(owner=owner, source_id=source.pk)
    client.force_login(owner)
    result = submit(client, "2026-10-26T10:00", "2026-10-26T11:00").context["result"]
    assert not result["available"]
    assert result["conflicts"][0]["title"] == "Private class"


def test_one_off_cancellation_changes_result_on_next_check(client, owner, source):
    window(owner, WindowSpec(0, time(8), time(20)))
    series = rule(owner, source)
    client.force_login(owner)
    assert not submit(client, "2026-10-26T10:00", "2026-10-26T11:00").context["result"]["available"]
    cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=MONDAY)
    assert submit(client, "2026-10-26T10:00", "2026-10-26T11:00").context["result"]["available"]


def test_foreign_schedule_is_not_included_even_with_forged_owner(client, owner, other_owner, other_source, halifax_time):
    window(owner, WindowSpec(0, time(8), time(20)))
    rule(other_owner, other_source)
    Commitment.objects.create(source=other_source, title="Other account secret",
                              starts_at=halifax_time("2026-10-26T09:00"), ends_at=halifax_time("2026-10-26T14:00"))
    client.force_login(owner)
    response = submit(client, owner=other_owner.pk, source=other_source.pk)
    assert response.context["result"]["available"]
    assert other_source.name.encode() not in response.content
    assert b"Other account secret" not in response.content


@pytest.mark.parametrize("kind", ["working", "commitment"])
def test_invalid_dst_schedule_needs_review_and_keeps_known_conflict(client, owner, source, halifax_time, kind):
    day = date(2026, 3, 8)
    window(owner, WindowSpec(6, time(8), time(20)),
           *([WindowSpec(6, time(2, 30), time(3))] if kind == "working" else []), effective_from=day)
    if kind == "commitment":
        rule(owner, source, starts_on=day, weekdays=[6], start_time=time(2, 30), end_time=time(3))
    Commitment.objects.create(source=source, title="Known conflict", starts_at=halifax_time("2026-03-08T09:00"),
                              ends_at=halifax_time("2026-03-08T10:00"))
    client.force_login(owner)
    response = submit(client, "2026-03-08T09:00", "2026-03-08T10:00")
    result = response.context["result"]
    assert not result["complete"] and not result["available"]
    assert result["conflicts"][0]["title"] == "Known conflict"
    assert b"Needs review" in response.content
    assert b"Available for this shift" not in response.content
    assert result["review_working" if kind == "working" else "review_commitments"] == [day]


@pytest.mark.parametrize("starts,ends", [
    ("", "2026-10-26T10:00"), ("bad", "2026-10-26T10:00"),
    ("2026-02-30T09:00", "2026-10-26T10:00"),
    ("2026-10-26T10:00", "2026-10-26T09:00"),
    ("2026-10-26T10:00", "2026-10-26T10:00"),
    ("2026-10-26T09:00Z", "2026-10-26T10:00"),
    ("2026-10-26", "2026-10-26T10:00"),
    ("0001-01-01T09:00", "0001-01-01T10:00"),
    ("9999-12-31T09:00", "9999-12-31T10:00"),
    ("2026-01-01T09:00", "2027-01-03T09:00"),
])
def test_invalid_inputs_redisplay_errors_without_result(client, owner, starts, ends):
    client.force_login(owner)
    response = submit(client, starts, ends)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert "result" not in response.context
    assert response["Cache-Control"] == "private, no-store"


def test_missing_clock_moves_forward_and_uses_resolved_interval(client, owner):
    window(owner, WindowSpec(6, time(3), time(5)), effective_from=date(2026, 3, 8))
    client.force_login(owner)
    response = submit(client, "2026-03-08T02:15", "2026-03-08T04:00")
    assert response.context["result"]["available"]
    assert response.context["result"]["starts_at"].hour == 3
    assert b"moved forward for the clock change" in response.content
    assert b"03:15 ADT" in response.content


def test_resolved_reversed_interval_is_rejected(client, owner):
    client.force_login(owner)
    response = submit(client, "2026-03-08T02:30", "2026-03-08T03:00")
    assert "ends_at" in response.context["form"].errors
    assert "result" not in response.context


def test_repeated_time_defaults_first_and_accepts_explicit_second_end(client, owner):
    window(owner, WindowSpec(6, time(0), time(3)), effective_from=date(2026, 11, 1))
    client.force_login(owner)
    response = submit(client, "2026-11-01T01:15", "2026-11-01T01:45")
    assert response.context["result"]["available"]
    assert b"first repeated time" in response.content
    response = submit(client, "2026-11-01T01:45", "2026-11-01T01:15", second_end="on")
    result = response.context["result"]
    assert result["available"]
    assert result["starts_at"].tzname() == "ADT" and result["ends_at"].tzname() == "AST"
    assert (result["ends_at"].astimezone(UTC) - result["starts_at"].astimezone(UTC)).seconds == 1800
    assert b"second repeated time" in response.content


def test_second_hour_option_rejects_nonrepeated_clock(client, owner):
    client.force_login(owner)
    response = submit(client, second_start="on")
    assert "starts_at" in response.context["form"].errors
    assert b"Clear the second-hour option" in response.content
    assert b'<details class="shift-clock-options" open' in response.content
    assert "result" not in response.context


def test_form_and_result_do_not_follow_device_timezone(client, owner):
    window(owner, WindowSpec(0, time(8), time(20)))
    client.force_login(owner)
    with timezone.override("Asia/Tokyo"):
        response = submit(client)
    assert response.context["result"]["starts_at"].hour == 9
    assert b"09:00 ADT" in response.content


def test_second_start_can_choose_later_instant_and_fractional_seconds_are_preserved(client, owner):
    window(owner, WindowSpec(6, time(0), time(3)), effective_from=date(2026, 11, 1))
    client.force_login(owner)
    response = submit(client, "2026-11-01T01:15:00.5", "2026-11-01T01:15:01", second_start="on", second_end="on")
    assert response.context["result"]["available"]
    assert b"01:15:00.5 AST" in response.content
    assert b"01:15:01 AST" in response.content


def test_moved_in_exception_is_checked_on_its_actual_date(client, owner, source, halifax_time):
    window(owner, WindowSpec(1, time(8), time(20)))
    series = rule(owner, source)
    reschedule_occurrence(owner=owner, series_id=series.pk, original_start_date=MONDAY,
                          replacement_source_id=source.pk, replacement_title="Moved class",
                          starts_at=halifax_time("2026-10-27T09:00"), ends_at=halifax_time("2026-10-27T10:00"))
    client.force_login(owner)
    result = submit(client, "2026-10-27T09:00", "2026-10-27T10:00").context["result"]
    assert result["conflicts"][0]["title"] == "Moved class"
    assert not result["available"]


def test_shift_form_uses_csrf_protection(owner):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    assert submit(client).status_code == 403


def test_shift_presentation_queries_are_bounded(owner, source, halifax_time, django_assert_max_num_queries):
    window(owner, WindowSpec(0, time(8), time(20)))
    for index in range(12):
        rule(owner, source, title=f"Class {index}")
    with django_assert_max_num_queries(10):
        result = shift_screen_for_user(owner=owner, starts_at=halifax_time("2026-10-26T10:00"),
                                       ends_at=halifax_time("2026-10-26T11:00"))
    assert len(result["conflicts"]) == 12
