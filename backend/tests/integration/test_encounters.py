import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.encounters.models import Encounter
from apps.encounters.services import create_encounter
from apps.spatial.models import Spot
from tests.integration.test_spatial import projected_point

pytestmark = pytest.mark.django_db
ORIGIN = {"latitude": 37.5665, "longitude": 126.978}
URL = "/api/v1/encounters"


def payload(rule):
    return {"spot_id": str(rule.spot_id), **ORIGIN}


def test_creation_reuse_and_owner_read(authenticated, user, spawn_rule):
    first = authenticated.post(URL, payload(spawn_rule))
    assert first.status_code == 201
    data = first.data
    obj = Encounter.objects.get()
    assert obj.user == user
    assert obj.character_variant_id == spawn_rule.character_variant_id
    assert obj.expires_at - obj.spawned_at == timedelta(seconds=180)
    second = authenticated.post(URL, payload(spawn_rule))
    assert second.status_code == 200
    assert second.data == data
    assert Encounter.objects.count() == 1
    assert authenticated.get(f"{URL}/{obj.id}").data == data
    assert APIClient().post(URL, payload(spawn_rule)).status_code == 401
    assert APIClient().get(f"{URL}/{obj.id}").status_code == 401
    assert authenticated.get(f"{URL}/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"latitude": 91},
        {"longitude": 181},
        {"latitude": "NaN"},
        {"longitude": "Infinity"},
        {"latitude": "-Infinity"},
        {"spot_id": "invalid"},
        {"character_variant_id": str(uuid.UUID(int=1))},
        {"status": "active"},
        {"expires_at": "2099-01-01T00:00:00Z"},
        {"user": str(uuid.UUID(int=1))},
    ],
)
def test_invalid_input(authenticated, spawn_rule, changes):
    response = authenticated.post(URL, {**payload(spawn_rule), **changes})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert not Encounter.objects.exists()


@pytest.mark.parametrize("missing", ["spot_id", "latitude", "longitude"])
def test_missing_input(authenticated, spawn_rule, missing):
    data = payload(spawn_rule)
    del data[missing]
    assert authenticated.post(URL, data).status_code == 400


@pytest.mark.parametrize("inactive", [True, False])
def test_unavailable_spot(authenticated, spawn_rule, inactive):
    data = payload(spawn_rule)
    if inactive:
        Spot.objects.filter(pk=spawn_rule.spot_id).update(is_active=False)
    else:
        data["spot_id"] = str(uuid.uuid4())
    assert authenticated.post(URL, data).status_code == 404
    assert not Encounter.objects.exists()


@pytest.mark.parametrize("distance,status", [(99.999, 201), (100.001, 403)])
def test_geography_distance_boundary(authenticated, spawn_rule, distance, status):
    Spot.objects.filter(pk=spawn_rule.spot_id).update(location=projected_point(distance))
    response = authenticated.post(URL, payload(spawn_rule))
    assert response.status_code == status
    if status == 403:
        assert response.data["error"]["details"]["reason"] == "out_of_range"
        assert not Encounter.objects.exists()


@pytest.mark.parametrize(
    "change", ["delete", "inactive", "future", "ended", "variant", "character"]
)
def test_no_eligible_rule(authenticated, spawn_rule, change):
    data = payload(spawn_rule)
    if change == "delete":
        spawn_rule.delete()
    elif change in {"variant", "character"}:
        obj = spawn_rule.character_variant
        if change == "character":
            obj = obj.character
        obj.is_active = False
        obj.save()
    else:
        if change == "inactive":
            spawn_rule.is_active = False
        elif change == "future":
            spawn_rule.starts_at = timezone.now() + timedelta(days=1)
        else:
            spawn_rule.ends_at = timezone.now() - timedelta(seconds=1)
        spawn_rule.save()
    response = authenticated.post(URL, data)
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"
    assert response.data["error"]["details"]["reason"] == "no_spawn_rule"
    assert not Encounter.objects.exists()


@pytest.mark.parametrize("change", ["rule", "period", "variant", "character"])
def test_existing_result_survives_rule_and_catalog_changes(authenticated, spawn_rule, change):
    initial = authenticated.post(URL, payload(spawn_rule))
    obj = spawn_rule
    if change == "period":
        obj.ends_at = timezone.now() - timedelta(seconds=1)
    else:
        if change in {"variant", "character"}:
            obj = spawn_rule.character_variant
            if change == "character":
                obj = obj.character
        obj.is_active = False
    obj.save()
    response = authenticated.post(URL, payload(spawn_rule))
    assert response.status_code == 200
    assert response.data == initial.data
    assert authenticated.post(URL, {**payload(spawn_rule), "latitude": 0}).status_code == 403
    Spot.objects.filter(pk=spawn_rule.spot_id).update(is_active=False)
    assert authenticated.post(URL, payload(spawn_rule)).status_code == 404
    assert authenticated.get(f"{URL}/{initial.data['id']}").status_code == 200


@pytest.mark.parametrize("delta,status", [(-1, "active"), (0, "expired"), (1, "expired")])
def test_effective_expiry_read_does_not_write(
    authenticated, spawn_rule, monkeypatch, delta, status
):
    response = authenticated.post(URL, payload(spawn_rule))
    obj = Encounter.objects.get()
    now = obj.expires_at + timedelta(microseconds=delta)
    monkeypatch.setattr("apps.encounters.models.timezone.now", lambda: now)
    response = authenticated.get(f"{URL}/{obj.id}")
    assert response.data["status"] == status
    obj.refresh_from_db()
    assert obj.status == "active"


def test_expired_replaced_and_other_user_isolated(authenticated, user, spawn_rule):
    from apps.accounts.models import User

    initial = authenticated.post(URL, payload(spawn_rule))
    old = Encounter.objects.get()
    Encounter.objects.filter(pk=old.pk).update(
        spawned_at=timezone.now() - timedelta(minutes=4),
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    response = authenticated.post(URL, payload(spawn_rule))
    assert response.status_code == 201
    assert response.data["id"] != initial.data["id"]
    old.refresh_from_db()
    assert old.status == "expired"
    other = User.objects.create_user("other@example.com", "password")
    authenticated.force_authenticate(other)
    assert authenticated.get(f"{URL}/{response.data['id']}").status_code == 404
    assert authenticated.post(URL, payload(spawn_rule)).status_code == 201
    assert Encounter.objects.filter(status="active").count() == 2


@pytest.mark.parametrize("changes", [{"status": "unknown"}, {"expires_at": None}])
def test_encounter_constraints(user, spawn_rule, changes):
    obj, _ = create_encounter(user=user, spot_id=spawn_rule.spot_id, **ORIGIN)
    with pytest.raises(IntegrityError), transaction.atomic():
        Encounter.objects.filter(pk=obj.pk).update(**changes)
    with pytest.raises(IntegrityError), transaction.atomic():
        Encounter.objects.filter(pk=obj.pk).update(expires_at=obj.spawned_at)
    with pytest.raises(IntegrityError), transaction.atomic():
        Encounter.objects.create(
            user=user,
            spot=obj.spot,
            character_variant=obj.character_variant,
            spawned_at=obj.spawned_at,
            expires_at=obj.expires_at,
        )


@pytest.mark.parametrize("stage", ["expire", "insert"])
def test_creation_rolls_back_expiry_and_insert(authenticated, spawn_rule, monkeypatch, stage):
    authenticated.post(URL, payload(spawn_rule))
    old = Encounter.objects.get()
    Encounter.objects.filter(pk=old.pk).update(
        spawned_at=timezone.now() - timedelta(minutes=4),
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    original = Encounter.save

    def fail_after_write(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if (stage == "expire" and self.pk == old.pk) or (stage == "insert" and self.pk != old.pk):
            raise RuntimeError("Injected encounter write failure")

    monkeypatch.setattr(Encounter, "save", fail_after_write)
    assert authenticated.post(URL, payload(spawn_rule)).status_code == 500
    old.refresh_from_db()
    assert old.status == "active"
    assert Encounter.objects.count() == 1


def test_interaction_boundary_uses_postgis_distance(spawn_rule):
    from apps.spatial.selectors import nearby_spots, within_interaction_radius

    spot = spawn_rule.spot
    spot.location = projected_point(100)
    spot.save()
    distance = nearby_spots(**ORIGIN, radius_m=101).get(pk=spot.pk).distance.m
    # ST_Project/geometry round trips have sub-millimeter floating-point error.
    # Bracket the measured geography boundary without widening the production radius.
    spot.interaction_radius_m = distance + 0.0001
    assert within_interaction_radius(spot=spot, **ORIGIN)
    spot.interaction_radius_m = distance - 0.0001
    assert not within_interaction_radius(spot=spot, **ORIGIN)


def test_bearer_jwt_and_json_creation(client, user, spawn_rule):
    from rest_framework_simplejwt.tokens import RefreshToken

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    assert client.post(URL, payload(spawn_rule), format="json").status_code == 201
    user.is_active = False
    user.save()
    assert client.post(URL, payload(spawn_rule), format="json").status_code == 401
    assert Encounter.objects.count() == 1


def test_multi_variant_selection_filters_before_weighting(authenticated, spawn_rule, monkeypatch):
    from apps.characters.models import CharacterVariant
    from apps.encounters.models import SpawnRule

    variant = CharacterVariant.objects.create(
        character=spawn_rule.character_variant.character, code="second", name="Second"
    )
    second = SpawnRule.objects.create(spot=spawn_rule.spot, character_variant=variant, weight=3)
    inactive = CharacterVariant.objects.create(
        character=variant.character, code="inactive", name="Inactive", is_active=False
    )
    SpawnRule.objects.create(spot=spawn_rule.spot, character_variant=inactive, weight=999)
    ordered = sorted([spawn_rule, second], key=lambda rule: rule.id)
    offset = 0 if ordered[0].pk == second.pk else ordered[0].weight

    def draw(total):
        assert total == 4
        return offset

    monkeypatch.setattr("apps.encounters.services.secrets.randbelow", draw)
    response = authenticated.post(URL, payload(spawn_rule), format="json")
    assert response.status_code == 201
    assert response.data["character_variant_id"] == str(variant.id)


def test_failed_replacement_without_rules_preserves_old_row(authenticated, spawn_rule):
    authenticated.post(URL, payload(spawn_rule))
    old = Encounter.objects.get()
    Encounter.objects.filter(pk=old.pk).update(
        spawned_at=timezone.now() - timedelta(minutes=4),
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    spawn_rule.is_active = False
    spawn_rule.save()
    assert authenticated.post(URL, payload(spawn_rule)).status_code == 409
    old.refresh_from_db()
    assert old.status == "active"
    assert old.effective_status() == "expired"
    assert Encounter.objects.count() == 1
