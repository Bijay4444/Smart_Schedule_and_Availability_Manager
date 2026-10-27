from datetime import UTC, datetime

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
