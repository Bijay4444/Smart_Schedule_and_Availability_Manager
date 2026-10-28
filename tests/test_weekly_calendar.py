from datetime import date, datetime, time

import pytest
from django.urls import reverse

from scheduling.calendar import calendar_for_user
from scheduling.models import Commitment
from scheduling.recurrence import cancel_occurrence, create_series, reschedule_occurrence
from scheduling.services import archive_source


pytestmark = pytest.mark.django_db


def test_calendar_requires_login(client):
    response = client.get(reverse("scheduling:week"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login") + "?next=")


def test_empty_calendar_has_seven_days_navigation_and_date_specific_add_links(client, owner):
    client.force_login(owner)
    response = client.get(reverse("scheduling:week"), {"week": "2026-10-29"})
    assert response.status_code == 200
    week = response.context["week"]
    assert week["start"] == date(2026, 10, 26)
    assert week["end"] == date(2026, 11, 1)
    assert len(week["days"]) == 7
    assert week["previous"] == date(2026, 10, 19)
    assert week["next"] == date(2026, 11, 2)
    assert b"A fresh page for your week" in response.content
    assert b"date=2026-10-28&amp;week=2026-10-26" in response.content
    assert b"Add your first source" in response.content
    assert b"America/Halifax" in response.content
    assert not Commitment.objects.exists()


@pytest.mark.parametrize("value", ["", "invalid", "2026-02-30", "2026-W44-1", "0001-01-01", "9999-12-31"])
def test_invalid_week_returns_bad_request_instead_of_server_error(client, owner, value):
    client.force_login(owner)
    assert client.get(reverse("scheduling:week"), {"week": value}).status_code == 400


def test_calendar_does_not_disclose_other_users_titles_sources_or_conflicts(
    client, owner, commitment, other_source
):
    Commitment.objects.create(source=other_source, title="Confidential appointment",
                              starts_at=commitment.starts_at, ends_at=commitment.ends_at)
    client.force_login(owner)
    response = client.get(reverse("scheduling:week"), {"week": "2026-10-26", "owner": other_source.owner_id})
    assert response.status_code == 200
    assert response.context["week"]["entry_count"] == 1
    assert response.context["week"]["conflict_count"] == 0
    assert b"Morning shift" in response.content
    assert b"Confidential appointment" not in response.content
    assert other_source.name.encode() not in response.content


def test_overnight_splits_across_days_and_displayed_weeks(owner, source, halifax_time):
    item = Commitment.objects.create(
        source=source, title="Sunday overnight", starts_at=halifax_time("2026-10-25T22:00"),
        ends_at=halifax_time("2026-10-26T06:00"),
    )
    previous = calendar_for_user(owner=owner, anchor=date(2026, 10, 19))
    current = calendar_for_user(owner=owner, anchor=date(2026, 10, 26))
    sunday = previous["days"][6].blocks[0]
    monday = current["days"][0].blocks[0]
    assert sunday.entry.commitment_id == monday.entry.commitment_id == item.pk
    assert sunday.continues_after and not sunday.continues_before
    assert monday.continues_before and not monday.continues_after
    assert sunday.end_label == "24:00"
    assert monday.start_label == "00:00 ADT"
    assert monday.height_minutes == 360


def test_calendar_includes_recurring_moves_and_omits_cancellations(owner, source, halifax_time):
    series = create_series(
        owner=owner, source_id=source.pk, title="Seminar", starts_on=date(2026, 10, 26),
        weekdays=[0, 2], start_time=time(9), end_time=time(11),
    )
    cancel_occurrence(owner=owner, series_id=series.pk, original_start_date=date(2026, 10, 26))
    reschedule_occurrence(
        owner=owner, series_id=series.pk, original_start_date=date(2026, 10, 28),
        replacement_source_id=source.pk, replacement_title="Moved seminar",
        starts_at=halifax_time("2026-11-03T09:00"), ends_at=halifax_time("2026-11-03T11:00"),
    )
    assert calendar_for_user(owner=owner, anchor=date(2026, 10, 26))["entry_count"] == 0
    next_week = calendar_for_user(owner=owner, anchor=date(2026, 11, 2))
    moved = next_week["days"][1].blocks[0]
    assert moved.entry.title == "Moved seminar"
    assert moved.entry.kind == "Rescheduled"
    assert moved.entry.commitment_id is None


def test_visible_overlaps_have_separate_lanes_but_touching_intervals_do_not_conflict(
    owner, source, commitment, halifax_time
):
    Commitment.objects.create(source=source, title="Overlap", starts_at=halifax_time("2026-10-26T11:00"), ends_at=halifax_time("2026-10-26T12:00"))
    Commitment.objects.create(source=source, title="Adjacent", starts_at=halifax_time("2026-10-26T12:00"), ends_at=halifax_time("2026-10-26T13:00"))
    week = calendar_for_user(owner=owner, anchor=date(2026, 10, 26))
    blocks = week["days"][0].blocks
    assert week["conflict_count"] == 2
    assert blocks[0].width_percent == blocks[1].width_percent == "50.00000"
    assert blocks[0].left_percent != blocks[1].left_percent
    assert not blocks[2].entry.has_conflict
    assert blocks[2].width_percent == "100.00000"


def test_one_time_and_recurring_conflict_is_visible(owner, source, commitment):
    create_series(owner=owner, source_id=source.pk, title="Seminar", starts_on=date(2026, 10, 26),
                  weekdays=[0], start_time=time(11), end_time=time(13))
    week = calendar_for_user(owner=owner, anchor=date(2026, 10, 26))
    assert week["conflict_count"] == 2
    assert all(block.entry.has_conflict for block in week["days"][0].blocks)


def test_repeated_hour_keeps_positive_visual_duration_and_distinct_offset_labels(owner, source, halifax_time):
    Commitment.objects.create(
        source=source, title="Across repeated hour",
        starts_at=halifax_time("2026-11-01T01:45").replace(fold=0),
        ends_at=halifax_time("2026-11-01T01:15").replace(fold=1),
    )
    week = calendar_for_user(owner=owner, anchor=date(2026, 10, 26))
    sunday = week["days"][6]
    assert sunday.minutes == 1500
    block = sunday.blocks[0]
    assert block.top_minutes == 105
    assert block.height_minutes == 30
    assert block.start_label == "01:45 ADT"
    assert block.end_label == "01:15 AST"
    assert sum(hour["label"] == "01:00" for hour in sunday.hours) == 2


def test_spring_forward_day_uses_23_hours_and_shows_gap_resolution(client, owner, source):
    create_series(owner=owner, source_id=source.pk, title="Early shift", starts_on=date(2026, 3, 1),
                  weekdays=[6], start_time=time(2, 30), end_time=time(4))
    client.force_login(owner)
    response = client.get(reverse("scheduling:week"), {"week": "2026-03-02"})
    sunday = response.context["week"]["days"][6]
    assert sunday.minutes == 1380
    assert sunday.blocks[0].height_minutes == 30
    assert b"moved forward for the clock change" in response.content
    assert b"23-hour day" in response.content


def test_invalid_dst_interval_is_a_visible_review_issue(client, owner, source):
    create_series(owner=owner, source_id=source.pk, title="Needs review", starts_on=date(2026, 3, 1),
                  weekdays=[6], start_time=time(2, 30), end_time=time(3))
    client.force_login(owner)
    response = client.get(reverse("scheduling:week"), {"week": "2026-03-02"})
    assert not response.context["week"]["complete"]
    assert b"Some times need a closer look" in response.content
    assert b"Needs review" in response.content
    assert b"A fresh page for your week" not in response.content


def test_archived_source_entries_remain_visible_and_text_is_escaped(client, owner, commitment):
    commitment.title = "<script>alert('private')</script>"
    commitment.save()
    archive_source(source_id=commitment.source_id, owner=owner)
    client.force_login(owner)
    response = client.get(reverse("scheduling:week"), {"week": "2026-10-26"})
    assert response.context["week"]["entry_count"] == 1
    assert commitment.source in response.context["week"]["sources"]
    assert b"<script>alert" not in response.content
    assert b"&lt;script&gt;" in response.content


def test_day_link_prefills_form_and_save_returns_to_week(client, owner, source):
    client.force_login(owner)
    url = reverse("scheduling:commitment_create") + "?date=2026-10-28&week=2026-10-26"
    response = client.get(url)
    assert response.context["form"].initial["starts_at"] == datetime(2026, 10, 28, 9)
    assert response.context["form"].initial["ends_at"] == datetime(2026, 10, 28, 10)
    response = client.post(url, {"title": "Class", "source": source.pk,
                                "starts_at": "2026-10-28T09:00", "ends_at": "2026-10-28T10:00"})
    assert response.status_code == 302
    assert response.url == reverse("scheduling:week") + "?week=2026-10-26"


def test_bad_date_and_external_week_cannot_set_redirect_or_modify_edit_initial(client, owner, commitment):
    client.force_login(owner)
    response = client.get(reverse("scheduling:commitment_create"), {"date": "invalid", "week": "https://example.org"})
    assert response.status_code == 200
    assert "starts_at" not in response.context["form"].initial
    assert response.context["return_url"] == reverse("scheduling:commitment_list")
    response = client.get(reverse("scheduling:commitment_update", args=[commitment.pk]), {"date": "2026-10-28"})
    assert response.context["form"].initial["starts_at"] == commitment.starts_at
