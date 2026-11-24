from datetime import UTC, date, datetime, time, timedelta

import pytest
from django.core import signing
from django.urls import reverse
from django.test import Client

from scheduling.models import (
    Commitment, OccurrenceException, RecurringSeries, RevisionWeekday, SeriesRevision,
)
from scheduling.recurrence import create_series, occurrences_for_user, reschedule_occurrence
from scheduling.recurring_forms import OccurrenceChangeForm, SeriesCreateForm
from scheduling.recurring_workflow import ReviewRequired, save_occurrence_change, save_recurring_series
from scheduling.services import save_commitment


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("scheduling.recurrence.timezone.now", lambda: datetime(2026, 10, 26, 15, tzinfo=UTC))


@pytest.fixture
def values(source):
    return {"source_id": source.pk, "title": "Weekly class", "starts_on": MONDAY,
            "start_time": time(10), "end_time": time(12), "weekdays": [0]}


def preview(owner, values, **kwargs):
    with pytest.raises(ReviewRequired) as error:
        save_recurring_series(owner=owner, values=values, **kwargs)
    return error.value


def confirmed(owner, values, **kwargs):
    review = preview(owner, values, **kwargs)
    return save_recurring_series(owner=owner, values=values, review_token=review.token,
                                 confirmed=True, **kwargs)


def test_new_series_is_rolled_back_until_its_matching_review_is_confirmed(owner, values):
    review = preview(owner, values)
    assert not RecurringSeries.objects.exists()
    assert not SeriesRevision.objects.exists()
    assert not RevisionWeekday.objects.exists()
    assert review.preview.starts_on == MONDAY
    assert review.preview.through == date(2027, 10, 25)
    assert review.preview.limited
    assert len(review.preview.occurrences) == 53
    result = save_recurring_series(owner=owner, values=values, review_token=review.token, confirmed=True)
    assert RecurringSeries.objects.get().pk == result.pk


def test_review_warns_about_one_time_and_recurring_conflicts(owner, values, commitment):
    create_series(**{**values, "owner": owner, "title": "Other class"})
    review = preview(owner, {**values, "ends_on": MONDAY})
    assert {pair.other.title for pair in review.preview.conflicts} == {commitment.title, "Other class"}
    assert RecurringSeries.objects.count() == 1
    assert not review.preview.limited


def test_repeated_conflicts_are_grouped_without_losing_dates(owner, values):
    create_series(owner=owner, **{**values, "title": "Other weekly class"})
    review = preview(owner, values)
    groups = review.preview.conflict_groups
    assert len(groups) == 1
    assert groups[0]["count"] == len(review.preview.conflicts) == 53
    assert len(groups[0]["remaining"]) == 52


def test_changed_inputs_and_forged_or_missing_tokens_cannot_skip_review(owner, values):
    review = preview(owner, values)
    for token in (None, "forged", review.token):
        next_review = preview(owner, {**values, "title": "Changed input"}, review_token=token, confirmed=True)
        assert not RecurringSeries.objects.exists()
        assert next_review.preview.occurrences[0].title == "Changed input"


def test_new_conflict_after_review_requires_a_new_review(owner, values, source, halifax_time):
    review = preview(owner, values)
    save_commitment(owner=owner, commitment=Commitment(
        source=source, title="New shift", starts_at=halifax_time("2026-10-26T11:00"),
        ends_at=halifax_time("2026-10-26T13:00"),
    ))
    changed = preview(owner, values, review_token=review.token, confirmed=True)
    assert changed.changed
    assert changed.preview.conflicts[0].other.title == "New shift"
    assert not RecurringSeries.objects.exists()


def test_an_expired_review_cannot_save(owner, values, monkeypatch):
    review = preview(owner, values)
    # Force newly loaded tokens to appear old, while keeping recurrence's date fixed.
    monkeypatch.setattr("django.core.signing.time.time", lambda: 10**12)
    changed = preview(owner, values, review_token=review.token, confirmed=True)
    assert changed.changed
    assert not RecurringSeries.objects.exists()


def test_review_token_cannot_be_reused_by_another_owner(owner, values, other_owner, other_source):
    review = preview(owner, values)
    result = preview(other_owner, {**values, "source_id": other_source.pk}, review_token=review.token, confirmed=True)
    assert result.changed
    assert not RecurringSeries.objects.exists()


def test_future_revision_rolls_back_until_reviewed_and_preserves_exceptions(owner, values, source, halifax_time):
    rule = create_series(owner=owner, **values)
    move = reschedule_occurrence(owner=owner, series_id=rule.pk, original_start_date=date(2026, 11, 16),
                                 replacement_source_id=source.pk, replacement_title="Explicit hours",
                                 starts_at=halifax_time("2026-11-17T14:00"), ends_at=halifax_time("2026-11-17T16:00"))
    changes = {"title": "New hours", "effective_from": date(2026, 11, 16),
               "weekdays": [1], "start_time": time(9), "end_time": time(11)}
    review = preview(owner, changes, series_id=rule.pk)
    assert rule.revisions.count() == 1
    assert rule.revisions.get().effective_until is None
    assert move.pk in list(rule.exceptions.values_list("pk", flat=True))
    save_recurring_series(owner=owner, values=changes, series_id=rule.pk,
                          review_token=review.token, confirmed=True)
    assert rule.revisions.count() == 2
    assert rule.revisions.earliest("effective_from").effective_until == changes["effective_from"]
    assert rule.exceptions.get().pk == move.pk


def test_overlapping_overnight_occurrences_in_the_same_series_are_warned(owner, values):
    review = preview(owner, {**values, "start_time": time(22), "end_time": time(23),
                             "end_day_offset": 1, "weekdays": [0, 1], "ends_on": MONDAY + timedelta(days=1)})
    assert len(review.preview.conflicts) == 1
    assert review.preview.conflicts[0].candidate.series_id == review.preview.conflicts[0].other.series_id


def test_last_overnight_occurrence_is_checked_after_the_series_end(owner, values, source, halifax_time):
    sunday = date(2026, 11, 1)
    Commitment.objects.create(source=source, title="Monday class", starts_at=halifax_time("2026-11-02T05:00"),
                              ends_at=halifax_time("2026-11-02T07:00"))
    review = preview(owner, {**values, "starts_on": sunday, "ends_on": sunday, "weekdays": [6],
                             "start_time": time(22), "end_time": time(6), "end_day_offset": 1})
    assert review.preview.conflicts[0].other.title == "Monday class"


def test_dst_adjustments_and_invalid_occurrences_remain_visible(owner, values):
    day = date(2026, 3, 8)
    regular = {**values, "starts_on": day, "ends_on": day, "weekdays": [6], "start_time": time(2, 30)}
    adjusted = preview(owner, {**regular, "end_time": time(4)})
    assert adjusted.preview.adjustments[0].start_resolution.adjustment == "gap_shift_forward"
    invalid = preview(owner, {**regular, "end_time": time(3)})
    assert invalid.preview.issues
    assert not invalid.preview.occurrences


def test_dates_beyond_preview_are_not_claimed_checked_but_still_generate(owner, values, source, halifax_time):
    Commitment.objects.create(source=source, title="Distant shift", starts_at=halifax_time("2028-10-30T10:00"),
                              ends_at=halifax_time("2028-10-30T12:00"))
    review = preview(owner, values)
    assert review.preview.limited
    assert not review.preview.conflicts
    rule = save_recurring_series(owner=owner, values=values, review_token=review.token, confirmed=True)
    assert occurrences_for_user(owner=owner, starts_at=halifax_time("2028-10-30T00:00"),
                                ends_at=halifax_time("2028-10-31T00:00")).occurrences[0].series_id == rule.pk


def test_foreign_commitments_never_enter_review(owner, values, other_source, other_owner):
    create_series(owner=other_owner, **{**values, "source_id": other_source.pk})
    review = preview(owner, values)
    assert not review.preview.conflicts


def test_one_off_review_ignores_its_replaced_original_and_checks_other_occurrences(owner, values, source, halifax_time):
    rule = create_series(owner=owner, **values)
    changes = {"series_id": rule.pk, "original_start_date": MONDAY,
               "replacement_source_id": source.pk, "replacement_title": "Moved class",
               "starts_at": halifax_time("2026-10-26T11:00"), "ends_at": halifax_time("2026-10-26T13:00")}
    with pytest.raises(ReviewRequired) as error:
        save_occurrence_change(owner=owner, values=changes)
    assert not error.value.preview.conflicts
    assert not rule.exceptions.exists()
    save_occurrence_change(owner=owner, values=changes, review_token=error.value.token, confirmed=True)
    assert rule.exceptions.get().replacement_title == "Moved class"


def test_one_off_move_warns_against_another_occurrence_of_its_own_series(owner, values, source, halifax_time):
    rule = create_series(owner=owner, **{**values, "weekdays": [0, 1]})
    changes = {"series_id": rule.pk, "original_start_date": MONDAY,
               "replacement_source_id": source.pk, "replacement_title": "Moved Monday",
               "starts_at": halifax_time("2026-10-27T11:00"), "ends_at": halifax_time("2026-10-27T13:00")}
    with pytest.raises(ReviewRequired) as error:
        save_occurrence_change(owner=owner, values=changes)
    assert len(error.value.preview.conflicts) == 1
    assert error.value.preview.conflicts[0].other.original_start_date == date(2026, 10, 27)
    assert not rule.exceptions.exists()


@pytest.fixture
def post_data(source):
    return {"title": "Weekly class", "source": source.pk, "starts_on": "2026-10-26",
            "weekdays": ["0", "2"], "start_time": "10:00", "end_time": "12:00", "ends_on": ""}


def test_http_create_review_confirmation_and_private_list(client, owner, post_data):
    client.force_login(owner)
    url = reverse("scheduling:series_create")
    response = client.post(url, post_data)
    assert response.status_code == 200
    assert b"Review before saving" in response.content
    assert b"Dates after this range" in response.content
    assert not RecurringSeries.objects.exists()
    response = client.post(url, {**post_data, "confirm_review": "on", "review_token": response.context["form"]["review_token"].value()}, follow=True)
    assert response.status_code == 200
    assert RecurringSeries.objects.count() == 1
    assert b"Monday" in response.content and b"Wednesday" in response.content


def test_http_forged_confirmation_is_reviewed_not_saved(client, owner, post_data):
    client.force_login(owner)
    response = client.post(reverse("scheduling:series_create"), {**post_data, "confirm_review": "on", "review_token": "forged"})
    assert response.status_code == 200
    assert not RecurringSeries.objects.exists()
    assert response.context["form"]["confirm_review"].value() is False


@pytest.mark.parametrize("route", ["series_list", "series_create", "series_revise", "series_end", "occurrence_change", "occurrence_cancel"])
def test_recurring_routes_require_login(client, owner, values, route):
    rule = create_series(owner=owner, **values)
    kwargs = {"pk": rule.pk} if route not in ("series_list", "series_create") else {}
    if route.startswith("occurrence_"):
        kwargs["original_date"] = MONDAY.isoformat()
    response = client.get(reverse(f"scheduling:{route}", kwargs=kwargs))
    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.parametrize("route", ["series_revise", "series_end", "occurrence_change", "occurrence_cancel"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_recurring_object_routes_are_private(client, owner, values, other_owner, route, method):
    rule = create_series(owner=owner, **values)
    client.force_login(other_owner)
    kwargs = {"pk": rule.pk}
    if route.startswith("occurrence_"):
        kwargs["original_date"] = MONDAY.isoformat()
    assert getattr(client, method)(reverse(f"scheduling:{route}", kwargs=kwargs), {}).status_code == 404


def test_source_forgery_and_invalid_interval_are_form_errors(owner, post_data, other_source):
    form = SeriesCreateForm({**post_data, "source": other_source.pk}, owner=owner)
    assert not form.is_valid() and "source" in form.errors
    form = SeriesCreateForm({**post_data, "end_time": "09:00"}, owner=owner)
    assert not form.is_valid() and "end_time" in form.errors


def test_recurring_list_omits_foreign_sources_titles_and_exceptions(client, owner, values, other_owner, other_source):
    create_series(owner=other_owner, **{**values, "source_id": other_source.pk, "title": "Confidential class"})
    client.force_login(owner)
    response = client.get(reverse("scheduling:series_list"))
    assert b"Confidential class" not in response.content
    assert other_source.name.encode() not in response.content
    assert b"Add your first recurring commitment" in response.content


def test_cancel_and_end_require_post_and_confirmation(client, owner, values):
    rule = create_series(owner=owner, **values)
    client.force_login(owner)
    cancel = reverse("scheduling:occurrence_cancel", args=[rule.pk, MONDAY.isoformat()])
    assert client.get(cancel).status_code == 200
    assert not rule.exceptions.exists()
    assert client.post(cancel, {}).status_code == 200
    assert not rule.exceptions.exists()
    assert client.post(cancel, {"confirm": "on"}).status_code == 302
    assert rule.exceptions.get().kind == "cancel"
    end = reverse("scheduling:series_end", args=[rule.pk])
    assert client.get(end).status_code == 200
    rule.refresh_from_db()
    assert rule.ends_before is None
    assert client.post(end, {"confirm": "on", "ends_before": "2026-11-16"}).status_code == 302
    rule.refresh_from_db()
    assert rule.ends_before == date(2026, 11, 16)


def test_reschedule_form_resolves_missing_clock_and_accepts_second_repeated_hour(owner, values):
    rule = create_series(owner=owner, **{**values, "weekdays": [6], "starts_on": date(2026, 3, 1)})
    data = {"replacement_source": rule.source_id, "replacement_title": "Clock choice",
            "starts_at": "2026-11-01T01:15", "ends_at": "2026-11-01T01:45", "second_start": "on", "second_end": "on"}
    form = OccurrenceChangeForm(data, owner=owner, series=rule, original_date=date(2026, 11, 1))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["starts_at"].fold == 1
    assert "second repeated" in form.clock_notes[0]
    form = OccurrenceChangeForm({**data, "starts_at": "2026-03-08T02:15", "ends_at": "2026-03-08T04:00",
                                  "second_start": "", "second_end": ""}, owner=owner, series=rule, original_date=date(2026, 3, 8))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["starts_at"].hour == 3
    assert "moved forward" in form.clock_notes[0]


@pytest.mark.parametrize("route", ["series_create", "series_revise", "series_end", "occurrence_change", "occurrence_cancel"])
def test_recurring_routes_require_csrf(owner, values, route):
    rule = create_series(owner=owner, **values)
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    kwargs = {} if route == "series_create" else {"pk": rule.pk}
    if route.startswith("occurrence_"):
        kwargs["original_date"] = MONDAY.isoformat()
    assert client.post(reverse(f"scheduling:{route}", kwargs=kwargs), {}).status_code == 403


def test_calendar_links_target_stable_original_dates_after_a_move(client, owner, values, source, halifax_time):
    rule = create_series(owner=owner, **values)
    reschedule_occurrence(owner=owner, series_id=rule.pk, original_start_date=MONDAY,
                          replacement_source_id=source.pk, replacement_title="Moved",
                          starts_at=halifax_time("2026-10-27T14:00"), ends_at=halifax_time("2026-10-27T16:00"))
    client.force_login(owner)
    response = client.get(reverse("scheduling:week"), {"week": "2026-10-26"})
    target = reverse("scheduling:occurrence_change", args=[rule.pk, "2026-10-26"])
    assert target.encode() in response.content


def test_occurrence_route_rejects_a_date_without_an_occurrence(client, owner, values):
    rule = create_series(owner=owner, **values)
    client.force_login(owner)
    assert client.get(reverse("scheduling:occurrence_change", args=[rule.pk, "2026-10-27"])).status_code == 404
