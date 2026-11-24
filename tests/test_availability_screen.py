from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from html import escape

import pytest
from django.urls import reverse
from django.utils import timezone, translation

from scheduling.availability_presentation import availability_screen_for_user
from scheduling.intervals import Interval
from scheduling.models import Commitment
from scheduling.recurrence import create_series
from scheduling.working_windows import WindowSpec, set_working_date_override, set_working_schedule


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("scheduling.availability_presentation.timezone.now", lambda: datetime(2026, 10, 26, 15, tzinfo=UTC))


def schedule(owner, *windows, effective_from=MONDAY):
    return set_working_schedule(owner=owner, effective_from=effective_from, windows=windows)


def screen(owner, anchor=MONDAY):
    return availability_screen_for_user(owner=owner, anchor=anchor)


def test_acceptance_hours_and_share_projection_exclude_private_details(owner, source, halifax_time):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    create_series(owner=owner, source_id=source.pk, title="Private class title", starts_on=MONDAY,
                  start_time=time(10), end_time=time(12), weekdays=[0])
    Commitment.objects.create(source=source, title="Private study title",
                              starts_at=halifax_time("2026-10-26T12:00"), ends_at=halifax_time("2026-10-26T14:00"))
    result = screen(owner)
    assert result["complete"]
    assert result["total_label"] == "8h"
    assert result["available_day_count"] == 1
    assert [(item.start_label, item.end_label) for item in result["days"][0].slots] == [("08:00", "10:00"), ("14:00", "20:00")]
    assert "Mon 26 Oct: 08:00–10:00, 14:00–20:00" in result["share_text"]
    assert "Tue 27 Oct: Unavailable" in result["share_text"]
    assert "Time zone: America/Halifax" in result["share_text"]
    for private in (source.name, "Private class title", "Private study title", owner.username):
        assert private not in str(result)
    assert all("source" not in asdict(day) and "commitments" not in asdict(day) for day in result["days"])


def test_week_defaults_to_halifax_today_and_midweek_anchors_normalize_to_monday(owner):
    assert availability_screen_for_user(owner=owner)["starts_on"] == MONDAY
    result = screen(owner, date(2026, 10, 29))
    assert result["starts_on"] == MONDAY
    assert result["ends_on"] == date(2026, 11, 1)
    assert result["previous"] == date(2026, 10, 19)
    assert result["next"] == date(2026, 11, 2)


def test_no_windows_produces_empty_availability_with_setup_guidance(client, owner):
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"))
    assert response.status_code == 200
    result = response.context["availability"]
    assert not result["has_working_windows"]
    assert result["total_label"] == "0m"
    assert all(day.complete and not day.slots for day in result["days"])
    assert result["share_text"].count("Unavailable") == 7
    assert b"No working hours in this week" in response.content
    assert b"Set weekly working windows" in response.content


def test_fully_occupied_windows_are_not_reported_as_missing_configuration(owner, source, halifax_time):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    Commitment.objects.create(source=source, title="Occupied", starts_at=halifax_time("2026-10-26T08:00"),
                              ends_at=halifax_time("2026-10-26T20:00"))
    result = screen(owner)
    assert result["has_working_windows"]
    assert result["available_day_count"] == 0
    assert result["total_label"] == "0m"


def test_every_positive_gap_retains_second_and_microsecond_precision(owner, source, halifax_time):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    Commitment.objects.create(source=source, title="Long shift", starts_at=halifax_time("2026-10-26T08:00"),
                              ends_at=halifax_time("2026-10-26T19:59:59.500000"))
    result = screen(owner)
    assert "19:59:59.5–20:00" in result["share_text"]
    assert result["total_label"] == "0.5s"
    assert len(result["days"][0].slots) == 1


def test_overnight_slots_split_at_local_midnight_and_week_boundaries(owner):
    schedule(owner, WindowSpec(6, time(22), time(6), 1), effective_from=date(2026, 10, 19))
    result = screen(owner)
    assert "Mon 26 Oct: 00:00–06:00" in result["share_text"]
    assert "Sun 01 Nov: 22:00–24:00" in result["share_text"]
    next_week = screen(owner, date(2026, 11, 2))
    assert "Mon 02 Nov: 00:00–06:00" in next_week["share_text"]


def test_closed_date_removes_incoming_overnight_availability(owner):
    schedule(owner, WindowSpec(6, time(22), time(6), 1), effective_from=date(2026, 10, 19))
    set_working_date_override(owner=owner, local_date=MONDAY, intervals=[])
    result = screen(owner)
    assert not result["days"][0].slots
    assert "Mon 26 Oct: Unavailable" in result["share_text"]
    assert "Draft" not in result["share_text"]


@pytest.mark.parametrize("day,hours,six_elapsed", [(date(2026, 3, 8), 23, 5), (date(2026, 11, 1), 25, 7)])
def test_dst_day_duration_and_axis_use_elapsed_time(owner, halifax_time, day, hours, six_elapsed):
    set_working_date_override(owner=owner, local_date=day, intervals=[Interval(
        halifax_time(f"{day}T00:00"), halifax_time(f"{day + timedelta(days=1)}T00:00"),
    )])
    result = screen(owner, day)
    sunday = result["days"][6]
    assert sunday.elapsed_hours == hours
    assert result["total_label"] == f"{hours}h"
    assert float(sunday.axis[1]["percent"]) == pytest.approx(six_elapsed / hours * 100)
    assert float(sunday.slots[0].width_percent) == 100
    assert "24:00" in result["share_text"]
    assert "AST" in result["share_text"] and "ADT" in result["share_text"]


def test_repeated_hour_is_unambiguous_in_copied_text(owner, halifax_time):
    set_working_date_override(owner=owner, local_date=date(2026, 11, 1), intervals=[Interval(
        halifax_time("2026-11-01T01:15").replace(fold=0), halifax_time("2026-11-01T01:45").replace(fold=1),
    )])
    result = screen(owner, date(2026, 11, 1))
    assert "01:15 ADT–01:45 AST" in result["share_text"]
    assert result["total_label"] == "1h 30m"


def test_working_review_dates_are_marked_unknown_and_not_unavailable(client, owner):
    schedule(owner, WindowSpec(0, time(8), time(12)), WindowSpec(6, time(2, 30), time(3)), effective_from=date(2026, 3, 2))
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"), {"week": "2026-03-08"})
    result = response.context["availability"]
    assert not result["complete"]
    assert result["days"][6].review_working
    assert not result["days"][6].review_commitments
    assert not result["days"][6].slots
    assert "Draft:" in result["share_text"]
    assert "Sun 08 Mar: Needs review — availability not confirmed" in result["share_text"]
    assert "Sun 08 Mar: Unavailable" not in result["share_text"]
    assert "Mon 02 Mar: 08:00–12:00" in result["share_text"]
    assert b"Review working hours" in response.content


def test_commitment_review_does_not_disclose_its_reason_or_title(client, owner, source):
    day = date(2026, 3, 8)
    schedule(owner, WindowSpec(6, time(8), time(20)), effective_from=day)
    create_series(owner=owner, source_id=source.pk, title="Confidential medical commitment", starts_on=day,
                  ends_on=day, weekdays=[6], start_time=time(2, 30), end_time=time(3))
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"), {"week": day.isoformat()})
    result = response.context["availability"]
    assert not result["complete"]
    assert result["days"][6].review_commitments
    assert b"Review commitments" in response.content
    assert b"Confidential medical commitment" not in response.content
    assert source.name not in result["share_text"]
    assert "medical" not in result["share_text"]
    assert "Needs review" in result["share_text"]


def test_an_invalid_only_window_is_not_described_as_missing_configuration(client, owner):
    schedule(owner, WindowSpec(6, time(2, 30), time(3)), effective_from=date(2026, 3, 8))
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"), {"week": "2026-03-08"})
    assert b"Some dates need review" in response.content
    assert b"No working hours in this week" not in response.content


def test_privacy_is_enforced_for_other_users_windows_and_commitments(client, owner, other_owner, other_source, halifax_time):
    schedule(other_owner, WindowSpec(0, time(3, 17), time(5, 23)))
    Commitment.objects.create(source=other_source, title="Other private shift", starts_at=halifax_time("2026-10-26T03:17"),
                              ends_at=halifax_time("2026-10-26T05:23"))
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"))
    assert b"03:17" not in response.content and b"Other private shift" not in response.content
    assert other_source.name.encode() not in response.content
    assert not response.context["availability"]["has_working_windows"]


def test_owned_private_titles_never_reach_page_or_share_text(client, owner, source, halifax_time):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    title = '<script>alert("private")</script>'
    Commitment.objects.create(source=source, title=title, starts_at=halifax_time("2026-10-26T10:00"),
                              ends_at=halifax_time("2026-10-26T12:00"))
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"))
    assert title.encode() not in response.content
    assert escape(title).encode() not in response.content
    assert title not in response.context["availability"]["share_text"]
    assert owner.username not in response.context["availability"]["share_text"]


def test_availability_route_requires_login(client):
    response = client.get(reverse("scheduling:availability"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.parametrize("value", ["", "invalid", "20261026", "2026-02-30", "0001-01-01", "9999-12-31", "0002-01-01"])
def test_invalid_or_unsupported_week_is_a_bad_request(client, owner, value):
    client.force_login(owner)
    assert client.get(reverse("scheduling:availability"), {"week": value}).status_code == 400


def test_selected_week_navigation_and_calendar_links_preserve_monday(client, owner):
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"), {"week": "2026-10-29"})
    assert response.context["availability"]["starts_on"] == MONDAY
    assert b"?week=2026-10-19" in response.content and b"?week=2026-11-02" in response.content
    assert (reverse("scheduling:week") + "?week=2026-10-26").encode() in response.content
    calendar = client.get(reverse("scheduling:week"), {"week": "2026-10-29"})
    assert (reverse("scheduling:availability") + "?week=2026-10-26").encode() in calendar.content
    working = client.get(reverse("scheduling:working_windows"), {"date": "2026-10-29"})
    assert (reverse("scheduling:availability") + "?week=2026-10-26").encode() in working.content


def test_share_text_is_server_rendered_and_available_without_javascript(client, owner):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    client.force_login(owner)
    response = client.get(reverse("scheduling:availability"))
    assert b'<textarea' in response.content and b'readonly' in response.content
    assert b"Mon 26 Oct: 08:00" in response.content
    assert b"data-copy-availability hidden" in response.content
    assert b"select this text and copy it" in response.content
    assert response["Cache-Control"] == "private, no-store"


def test_refresh_recalculates_without_changing_saved_schedule(client, owner, source, halifax_time):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    client.force_login(owner)
    url = reverse("scheduling:availability")
    before = client.get(url).context["availability"]["share_text"]
    Commitment.objects.create(source=source, title="New shift", starts_at=halifax_time("2026-10-26T10:00"),
                              ends_at=halifax_time("2026-10-26T12:00"))
    after = client.get(url).context["availability"]["share_text"]
    assert "08:00–20:00" in before and "08:00–10:00, 12:00–20:00" in after
    assert Commitment.objects.count() == 1
    assert client.post(url, {}).status_code == 405


def test_display_zone_and_style_percentages_ignore_active_locale_and_zone(owner):
    schedule(owner, WindowSpec(0, time(8), time(20)))
    with timezone.override("UTC"), translation.override("de"):
        result = screen(owner)
    assert result["days"][0].slots[0].start_label == "08:00"
    assert "." in result["days"][0].slots[0].left_percent
    assert "," not in result["days"][0].slots[0].width_percent


def test_presentation_query_count_stays_bounded(owner, source, django_assert_max_num_queries):
    schedule(owner, *(WindowSpec(day, time(8), time(20)) for day in range(7)))
    for _ in range(6):
        create_series(owner=owner, source_id=source.pk, title="Private class", starts_on=MONDAY,
                      start_time=time(10), end_time=time(12), weekdays=[0, 2, 4])
    with django_assert_max_num_queries(10):
        result = screen(owner)
    assert len(result["days"]) == 7
    assert result["complete"]
