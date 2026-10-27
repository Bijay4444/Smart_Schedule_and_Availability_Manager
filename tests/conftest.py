from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scheduling.models import Commitment, CommitmentSource


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="schedule_owner")


@pytest.fixture
def other_owner(django_user_model):
    return django_user_model.objects.create_user(username="other_owner")


@pytest.fixture
def source(owner):
    return CommitmentSource.objects.create(owner=owner, name="Job A", color="#315c52")


@pytest.fixture
def other_source(other_owner):
    return CommitmentSource.objects.create(
        owner=other_owner, name="Private employer", color="#9261ba"
    )


@pytest.fixture
def halifax_time():
    def make_time(value):
        return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("America/Halifax"))

    return make_time


@pytest.fixture
def commitment(source, halifax_time):
    return Commitment.objects.create(
        source=source,
        title="Morning shift",
        starts_at=halifax_time("2026-10-26T10:00"),
        ends_at=halifax_time("2026-10-26T12:00"),
    )


@pytest.fixture
def commitment_data(source):
    return {
        "title": "Evening shift",
        "source": source.pk,
        "starts_at": "2026-10-26T16:00",
        "ends_at": "2026-10-26T20:00",
    }
