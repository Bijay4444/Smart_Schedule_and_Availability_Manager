from datetime import UTC, date, datetime, time

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError


@pytest.mark.django_db(transaction=True)
def test_recurring_migrations_preserve_legacy_one_time_rows_and_start_new_tables_empty():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old_target = [("scheduling", "0001_initial")]
    try:
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        user = old_apps.get_model("accounts", "User").objects.create(username="legacy_owner")
        source = old_apps.get_model("scheduling", "CommitmentSource").objects.create(
            owner_id=user.pk, name="Legacy source", color="#123456"
        )
        starts_at = datetime(2026, 11, 1, 1, tzinfo=UTC)
        ends_at = datetime(2026, 11, 1, 10, tzinfo=UTC)
        legacy = old_apps.get_model("scheduling", "Commitment").objects.create(
            source_id=source.pk, title="Legacy overnight shift", starts_at=starts_at, ends_at=ends_at
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        new_apps = executor.loader.project_state(latest).apps
        migrated = new_apps.get_model("scheduling", "Commitment").objects.get(pk=legacy.pk)
        migrated_source = new_apps.get_model("scheduling", "CommitmentSource").objects.get(pk=source.pk)
        assert (
            migrated.pk, migrated.source_id, migrated.title, migrated.starts_at, migrated.ends_at
        ) == (legacy.pk, source.pk, legacy.title, starts_at, ends_at)
        assert (migrated_source.owner_id, migrated_source.name, migrated_source.color) == (
            user.pk, source.name, source.color
        )
        assert migrated_source.archived_at is None
        for model in ["RecurringSeries", "SeriesRevision", "RevisionWeekday", "OccurrenceException"]:
            assert new_apps.get_model("scheduling", model).objects.count() == 0
        with pytest.raises(ProtectedError):
            migrated_source.delete()
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist')")
            assert cursor.fetchone()[0] is True
    finally:
        # Restore the schema even when an assertion fails, for following tests.
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_working_migration_preserves_recurring_rows_and_starts_working_tables_empty():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("scheduling", "0003_recurring_foundation")]
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("accounts", "User").objects.create(username="before_working")
        source = apps.get_model("scheduling", "CommitmentSource").objects.create(
            owner_id=user.pk, name="Classes", color="#123456",
        )
        series = apps.get_model("scheduling", "RecurringSeries").objects.create(
            source_id=source.pk, time_zone="America/Halifax", starts_on=date(2026, 10, 26),
        )
        revision = apps.get_model("scheduling", "SeriesRevision").objects.create(
            series_id=series.pk, effective_from=date(2026, 10, 26), title="Class",
            start_time=time(9), end_time=time(11),
        )
        weekday = apps.get_model("scheduling", "RevisionWeekday").objects.create(
            revision_id=revision.pk, weekday=0,
        )
        exception = apps.get_model("scheduling", "OccurrenceException").objects.create(
            series_id=series.pk, original_start_date=date(2026, 11, 2), kind="cancel",
        )
        before = {model: list(apps.get_model("scheduling", model).objects.values())
                  for model in ("CommitmentSource", "Commitment", "RecurringSeries", "SeriesRevision",
                                "RevisionWeekday", "OccurrenceException")}
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        for model, rows in before.items():
            assert list(apps.get_model("scheduling", model).objects.values()) == rows
        assert apps.get_model("scheduling", "RevisionWeekday").objects.get(pk=weekday.pk).weekday == 0
        assert apps.get_model("scheduling", "OccurrenceException").objects.get(pk=exception.pk).kind == "cancel"
        for model in ("WorkingScheduleRevision", "WorkingWindow", "WorkingDateOverride", "OverrideInterval"):
            assert not apps.get_model("scheduling", model).objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
