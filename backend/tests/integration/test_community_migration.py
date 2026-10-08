import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.encounters.services import capture_encounter


@pytest.mark.django_db(transaction=True)
def test_phase6_data_survives_community_upgrade(user, encounter):
    result = capture_encounter(user=user, encounter_id=encounter.pk)
    entry_id = result.collection_entry.pk
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("community", None)])
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        assert (
            apps.get_model("encounters", "Encounter").objects.get(pk=encounter.pk).status
            == "captured"
        )
        entry = apps.get_model("collection", "CollectionEntry").objects.get(pk=entry_id)
        assert entry.capture_result_id == result.pk
        for model in ("Post", "Comment", "Like", "Report"):
            assert not apps.get_model("community", model).objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
