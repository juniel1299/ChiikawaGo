import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.collection.models import CollectionEntry
from apps.encounters.models import CaptureResult, Encounter

pytestmark = pytest.mark.django_db


def url(encounter):
    return f"/api/v1/encounters/{encounter.pk}/capture"


def test_capture_jwt_success_and_replay_after_expiry(client, user, encounter, monkeypatch):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    first = client.post(url(encounter))
    assert first.status_code == 200
    encounter.refresh_from_db()
    assert encounter.status == "captured"
    result = CaptureResult.objects.get()
    entry = CollectionEntry.objects.get()
    assert result.encounter_id == encounter.id
    assert entry.user_id == user.id
    assert entry.character_variant_id == encounter.character_variant_id
    assert first.data["collection_entry_id"] == str(entry.id)
    assert first.data["captured_spot_id"] == str(encounter.spot_id)
    # Force authentication only for the clock jump; the first call above uses real JWT.
    client.force_authenticate(user)
    monkeypatch.setattr(
        "apps.encounters.models.timezone.now", lambda: encounter.expires_at + timedelta(days=1)
    )
    assert client.post(url(encounter), {}, format="json").data == first.data
    assert client.get(f"/api/v1/encounters/{encounter.id}").data["status"] == "captured"
    assert CaptureResult.objects.count() == CollectionEntry.objects.count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"success": True},
        {"latitude": 37},
        {"character_variant_id": "x"},
        {"user": "x"},
        {"reward": 10},
        [],
        None,
        "invalid",
    ],
)
def test_capture_input_rejected(authenticated, encounter, payload):
    if payload is None:
        response = authenticated.generic(
            "POST", url(encounter), data="null", content_type="application/json"
        )
    else:
        response = authenticated.post(url(encounter), data=payload, format="json")
    assert response.status_code == 400
    assert not CaptureResult.objects.exists()


def test_capture_auth_and_ownership(authenticated, user, encounter):
    assert APIClient().post(url(encounter)).status_code == 401
    other = User.objects.create_user("other@example.com", "password")
    authenticated.force_authenticate(other)
    assert authenticated.post(url(encounter)).status_code == 404
    assert authenticated.post(f"/api/v1/encounters/{uuid.uuid4()}/capture").status_code == 404
    assert authenticated.post("/api/v1/encounters/not-a-uuid/capture").status_code == 404
    authenticated.force_authenticate(None)
    authenticated.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
    )
    user.is_active = False
    user.save()
    assert authenticated.post(url(encounter)).status_code == 401
    assert not CaptureResult.objects.exists()


@pytest.mark.parametrize("offset,status", [(-1, 200), (0, 409), (1, 409)])
def test_capture_expiry_boundary(authenticated, encounter, monkeypatch, offset, status):
    now = encounter.expires_at + timedelta(microseconds=offset)
    monkeypatch.setattr("apps.encounters.services.timezone.now", lambda: now)
    response = authenticated.post(url(encounter))
    assert response.status_code == status
    encounter.refresh_from_db()
    if status == 409:
        assert response.data["error"]["details"]["reason"] == "encounter_expired"
        assert encounter.status == "active"
        assert not CaptureResult.objects.exists()
    else:
        assert CaptureResult.objects.get().captured_at == now


def test_stored_expired_is_rejected(authenticated, encounter):
    Encounter.objects.filter(pk=encounter.pk).update(status="expired")
    assert authenticated.post(url(encounter)).status_code == 409
    assert not CollectionEntry.objects.exists()


@pytest.mark.parametrize("target", ["spot", "rule", "variant", "character"])
def test_issued_encounter_survives_deactivation(authenticated, encounter, spawn_rule, target):
    obj = {
        "spot": spawn_rule.spot,
        "rule": spawn_rule,
        "variant": spawn_rule.character_variant,
        "character": spawn_rule.character_variant.character,
    }[target]
    obj.is_active = False
    obj.save()
    assert authenticated.post(url(encounter)).status_code == 200


@pytest.mark.parametrize(
    "stage", ["result_after", "entry_before", "entry_after", "status_before", "status_after"]
)
def test_capture_rollback(authenticated, encounter, monkeypatch, stage):
    model = (
        CaptureResult
        if stage.startswith("result")
        else CollectionEntry
        if stage.startswith("entry")
        else Encounter
    )
    original = model.save

    def fail(self, *args, **kwargs):
        if stage.endswith("before"):
            raise RuntimeError("Injected failure before capture write")
        original(self, *args, **kwargs)
        raise RuntimeError("Injected failure after capture write")

    monkeypatch.setattr(model, "save", fail)
    assert authenticated.post(url(encounter)).status_code == 500
    encounter.refresh_from_db()
    assert encounter.status == "active"
    assert not CaptureResult.objects.exists()
    assert not CollectionEntry.objects.exists()


@pytest.mark.parametrize(
    "corruption", ["no_result", "no_entry", "active_result", "wrong_owner", "wrong_variant"]
)
def test_inconsistent_capture_never_repairs_or_pays(
    authenticated, user, encounter, spawn_rule, corruption
):
    from apps.characters.models import CharacterVariant

    if corruption != "active_result":
        Encounter.objects.filter(pk=encounter.pk).update(status="captured")
    if corruption != "no_result":
        result = CaptureResult.objects.create(encounter=encounter, captured_at=timezone.now())
        if corruption in {"wrong_owner", "wrong_variant"}:
            owner = (
                User.objects.create_user("wrong@example.com", "pw")
                if corruption == "wrong_owner"
                else user
            )
            variant = (
                CharacterVariant.objects.create(
                    character=spawn_rule.character_variant.character, code="wrong", name="Wrong"
                )
                if corruption == "wrong_variant"
                else spawn_rule.character_variant
            )
            CollectionEntry.objects.create(
                capture_result=result, user=owner, character_variant=variant
            )
    counts = (CaptureResult.objects.count(), CollectionEntry.objects.count())
    response = authenticated.post(url(encounter))
    assert response.status_code == 500
    assert response.data["error"]["code"] == "internal_error"
    assert (CaptureResult.objects.count(), CollectionEntry.objects.count()) == counts


def test_one_to_one_constraints(authenticated, user, encounter):
    authenticated.post(url(encounter))
    result = CaptureResult.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        CaptureResult.objects.create(encounter=encounter, captured_at=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionEntry.objects.create(
            user=user, character_variant=encounter.character_variant, capture_result=result
        )


def test_mvp_end_to_end_api(client, spawn_rule):
    password = "Walking-in-the-park-42!"
    response = client.post(
        "/api/v1/auth/register",
        {"email": "mvp@example.com", "password": password, "display_name": "Walker"},
        format="json",
    )
    assert response.status_code == 201
    login = client.post("/api/v1/auth/token", {"email": "mvp@example.com", "password": password})
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    location = {"latitude": 37.5665, "longitude": 126.978}
    nearby = client.get("/api/v1/spots/nearby", location)
    spot_id = nearby.data["results"][0]["id"]
    ids = []
    for _ in range(2):
        created = client.post("/api/v1/encounters", {"spot_id": spot_id, **location}, format="json")
        assert created.status_code == 201
        captured = client.post(
            f"/api/v1/encounters/{created.data['id']}/capture", {}, format="json"
        )
        assert captured.status_code == 200
        ids.append(captured.data["collection_entry_id"])
    collection = client.get("/api/v1/collection")
    assert collection.data["count"] == 2
    assert {entry["id"] for entry in collection.data["results"]} == set(ids)
    assert {entry["character_variant"]["id"] for entry in collection.data["results"]} == {
        str(spawn_rule.character_variant_id)
    }
