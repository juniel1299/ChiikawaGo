from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_phase5_data_preserved_on_phase6_upgrade(user, spawn_rule):
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("collection", None), ("encounters", "0001_initial")])
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state([("encounters", "0001_initial")]).apps
        Encounter = apps.get_model("encounters", "Encounter")
        now = timezone.now()
        row = Encounter.objects.create(
            user_id=user.pk,
            spot_id=spawn_rule.spot_id,
            character_variant_id=spawn_rule.character_variant_id,
            spawned_at=now,
            expires_at=now + timedelta(seconds=180),
            status="active",
        )
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        restored = apps.get_model("encounters", "Encounter").objects.get(pk=row.pk)
        assert restored.status == "active"
        assert restored.spawned_at == now
        assert restored.expires_at == row.expires_at
        assert not apps.get_model("encounters", "CaptureResult").objects.exists()
        assert not apps.get_model("collection", "CollectionEntry").objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
