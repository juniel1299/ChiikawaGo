import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.collection.models import CollectionEntry
from apps.encounters.models import CaptureResult, Encounter
from apps.encounters.services import capture_encounter

pytestmark = pytest.mark.django_db


def test_collection_owner_current_catalog_and_no_n_plus_one(
    authenticated, user, encounter, spawn_rule
):
    assert APIClient().get("/api/v1/collection").status_code == 401
    assert authenticated.get("/api/v1/collection").data["count"] == 0
    capture_encounter(user=user, encounter_id=encounter.pk)
    variant = spawn_rule.character_variant
    variant.name, variant.rarity, variant.is_active = "Updated", "epic", False
    variant.save()
    character = variant.character
    character.name, character.is_active = "Renamed", False
    character.save()
    spot = spawn_rule.spot
    spot.name, spot.is_active = "New spot name", False
    spot.save()
    with CaptureQueriesContext(connection) as queries:
        response = authenticated.get("/api/v1/collection")
    assert len(queries) == 2  # count + joined page; force_authenticate avoids auth lookup.
    row = response.data["results"][0]
    assert row["character"]["name"] == "Renamed"
    assert row["character_variant"]["rarity"] == "epic"
    assert row["character_variant"]["name"] == "Updated"
    assert row["captured_spot"]["name"] == "New spot name"
    other = User.objects.create_user("outsider@example.com", "pw")
    authenticated.force_authenticate(other)
    assert authenticated.get("/api/v1/collection", {"user": str(user.pk)}).data["count"] == 0


def test_collection_pagination_and_fixed_tie_order(authenticated, user, spawn_rule):
    now = timezone.now()
    for index in range(105):
        encounter = Encounter.objects.create(
            user=user,
            spot=spawn_rule.spot,
            character_variant=spawn_rule.character_variant,
            status="captured",
            spawned_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=179),
        )
        result = CaptureResult.objects.create(encounter=encounter, captured_at=now)
        CollectionEntry.objects.create(
            id=uuid.UUID(int=index + 1),
            user=user,
            character_variant=spawn_rule.character_variant,
            capture_result=result,
        )
    with CaptureQueriesContext(connection) as queries:
        response = authenticated.get("/api/v1/collection")
    assert len(queries) == 2
    assert response.data["count"] == 105
    assert len(response.data["results"]) == 20
    assert response.data["results"][0]["id"] == str(uuid.UUID(int=105))
    second = authenticated.get("/api/v1/collection", {"page": 2})
    assert second.data["results"][0]["id"] == str(uuid.UUID(int=85))
    assert response.data["next"] and second.data["previous"]
    assert len(authenticated.get("/api/v1/collection", {"page_size": 500}).data["results"]) == 100
    assert authenticated.get("/api/v1/collection", {"page": 100}).status_code == 404
    assert (
        authenticated.get("/api/v1/collection", {"ordering": "id"}).data["results"]
        == response.data["results"]
    )
    first = CollectionEntry.objects.get(id=uuid.UUID(int=1))
    CaptureResult.objects.filter(pk=first.capture_result_id).update(
        captured_at=now + timedelta(seconds=1)
    )
    assert authenticated.get("/api/v1/collection").data["results"][0]["id"] == str(first.id)
