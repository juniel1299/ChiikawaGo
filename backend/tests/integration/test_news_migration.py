import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.encounters.services import capture_encounter


@pytest.mark.django_db(transaction=True)
def test_phase7_data_survives_news_upgrade(user, encounter, community_post):
    result = capture_encounter(user=user, encounter_id=encounter.pk)
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("news", None)])
        MigrationExecutor(connection).migrate(latest)
        apps = MigrationExecutor(connection).loader.project_state(latest).apps
        assert (
            apps.get_model("community", "Post").objects.get(pk=community_post.pk).content
            == community_post.content
        )
        assert (
            apps.get_model("collection", "CollectionEntry")
            .objects.get(capture_result_id=result.pk)
            .user_id
            == user.pk
        )
        for model in ("Source", "RawItem", "NewsCandidate", "News"):
            assert not apps.get_model("news", model).objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
