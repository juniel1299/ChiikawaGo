import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.encounters.services import capture_encounter
from apps.news.services import review_candidate


@pytest.mark.django_db(transaction=True)
def test_notifications_upgrade_preserves_existing_mvp(user, encounter, news_candidate, moderator):
    result = capture_encounter(user=user, encounter_id=encounter.pk)
    news = review_candidate(user=moderator, candidate_id=news_candidate.pk, action="approve")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("notifications", None)])
        MigrationExecutor(connection).migrate(latest)
        apps = MigrationExecutor(connection).loader.project_state(latest).apps
        assert apps.get_model("news", "News").objects.filter(pk=news.pk).exists()
        assert (
            apps.get_model("collection", "CollectionEntry")
            .objects.filter(capture_result_id=result.pk)
            .exists()
        )
        assert not apps.get_model("notifications", "PushDevice").objects.exists()
    finally:
        MigrationExecutor(connection).migrate(latest)
