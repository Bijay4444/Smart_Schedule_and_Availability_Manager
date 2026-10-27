from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from scheduling.forms import CommitmentForm, SourceForm
from scheduling.models import Commitment, CommitmentSource


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("end", ["2026-10-26T10:00", "2026-10-26T09:00"])
def test_invalid_intervals_fail_model_validation_and_database_constraint(
    source, halifax_time, end
):
    commitment = Commitment(
        source=source,
        title="Invalid shift",
        starts_at=halifax_time("2026-10-26T10:00"),
        ends_at=halifax_time(end),
    )

    with pytest.raises(ValidationError) as error:
        commitment.full_clean()
    assert "ends_at" in error.value.message_dict

    with pytest.raises(IntegrityError), transaction.atomic():
        commitment.save()
    assert not Commitment.objects.exists()


def test_source_name_is_unique_per_owner_but_can_be_shared_by_different_users(
    owner, other_owner, source
):
    other = CommitmentSource(owner=other_owner, name=source.name)
    other.full_clean()
    other.save()

    with pytest.raises(IntegrityError), transaction.atomic():
        CommitmentSource.objects.create(owner=owner, name=source.name)
    assert CommitmentSource.objects.count() == 2


@pytest.mark.parametrize("color", ["red", "#123", "#12345g", "#123456;display:none"])
def test_source_form_rejects_invalid_colors(owner, color):
    form = SourceForm(data={"name": "Classes", "color": color}, owner=owner)

    assert not form.is_valid()
    assert "color" in form.errors


def test_source_form_reports_duplicate_name_as_a_field_error(owner, source):
    form = SourceForm(data={"name": source.name, "color": "#123456"}, owner=owner)

    assert not form.is_valid()
    assert "name" in form.errors


def test_commitment_form_only_offers_the_owners_sources(owner, source, other_source):
    form = CommitmentForm(owner=owner)

    assert list(form.fields["source"].queryset) == [source]


def test_commitment_form_rejects_another_users_source(owner, other_source, commitment_data):
    form = CommitmentForm(
        data={**commitment_data, "source": other_source.pk}, owner=owner
    )

    assert not form.is_valid()
    assert "source" in form.errors


def test_overnight_form_input_is_aware_and_uses_explicit_dates(owner, commitment_data):
    form = CommitmentForm(
        data={
            **commitment_data,
            "starts_at": "2026-10-25T22:00",
            "ends_at": "2026-10-26T06:00",
        },
        owner=owner,
    )

    assert form.is_valid(), form.errors
    assert timezone.is_aware(form.cleaned_data["starts_at"])
    assert form.cleaned_data["starts_at"].day == 25
    assert form.cleaned_data["ends_at"].day == 26


def test_form_reports_an_end_before_start(owner, commitment_data):
    form = CommitmentForm(
        data={**commitment_data, "ends_at": "2026-10-26T15:00"}, owner=owner
    )

    assert not form.is_valid()
    assert "ends_at" in form.errors


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-03-08T02:30", "2026-03-08T04:00"),
        ("2026-11-01T01:30", "2026-11-01T03:00"),
    ],
)
def test_halifax_dst_ambiguous_or_missing_time_requires_clarification(
    owner, commitment_data, start, end
):
    with timezone.override("America/Halifax"):
        form = CommitmentForm(
            data={**commitment_data, "starts_at": start, "ends_at": end}, owner=owner
        )

        assert not form.is_valid()
        assert "starts_at" in form.errors


def test_model_validation_requires_time_zone_aware_values(source, halifax_time):
    commitment = Commitment(
        source=source,
        title="Unclear time zone",
        starts_at=halifax_time("2026-10-26T10:00").replace(tzinfo=None),
        ends_at=halifax_time("2026-10-26T12:00").replace(tzinfo=None),
    )

    with pytest.raises(ValidationError) as error:
        commitment.full_clean()

    assert {"starts_at", "ends_at"} <= error.value.message_dict.keys()


def test_explicit_fall_back_instants_validate_by_elapsed_time(source, halifax_time):
    commitment = Commitment(
        source=source,
        title="Across the repeated hour",
        starts_at=halifax_time("2026-11-01T01:45").replace(fold=0),
        ends_at=halifax_time("2026-11-01T01:15").replace(fold=1),
    )

    commitment.full_clean()
    commitment.save()
    commitment.refresh_from_db()

    assert commitment.ends_at - commitment.starts_at == timedelta(minutes=30)


def test_reversed_fall_back_instants_are_rejected(source, halifax_time):
    commitment = Commitment(
        source=source,
        title="End is earlier despite clock labels",
        starts_at=halifax_time("2026-11-01T01:15").replace(fold=1),
        ends_at=halifax_time("2026-11-01T01:45").replace(fold=0),
    )

    with pytest.raises(ValidationError) as error:
        commitment.full_clean()

    assert "ends_at" in error.value.message_dict
