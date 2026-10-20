import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from drf_spectacular.generators import SchemaGenerator

from apps.collection.models import CollectionEntry
from apps.encounters.admin import EffectiveStatusFilter
from apps.encounters.models import CaptureResult, Encounter
from apps.encounters.services import capture_encounter

pytestmark = pytest.mark.django_db


def resolve(schema, value):
    if "allOf" in value:
        value = value["allOf"][0]
    while "$ref" in value:
        value = schema["components"]["schemas"][value["$ref"].split("/")[-1]]
    return value


def check_object(schema, spec, actual):
    spec = resolve(schema, spec)
    assert spec["type"] == "object"
    assert set(spec["properties"]) == set(actual)
    assert set(spec["required"]) == set(actual)
    for name, value in actual.items():
        field = resolve(schema, spec["properties"][name])
        if isinstance(value, dict):
            check_object(schema, field, value)
        elif isinstance(value, str):
            assert field["type"] == "string"
            if "enum" in field:
                assert value in field["enum"]


def test_capture_and_collection_contract(authenticated, encounter):
    schema = SchemaGenerator().get_schema(public=True)
    path = "/api/v1/encounters/{id}/capture"
    operation = schema["paths"][path]["post"]
    response_spec = operation["responses"]["200"]["content"]["application/json"]["schema"]
    first = authenticated.post(f"/api/v1/encounters/{encounter.id}/capture")
    second = authenticated.post(f"/api/v1/encounters/{encounter.id}/capture", {}, format="json")
    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    check_object(schema, response_spec, first.data)
    assert "409" in operation["responses"]
    listing = authenticated.get("/api/v1/collection")
    spec = resolve(
        schema,
        schema["paths"]["/api/v1/collection"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"],
    )
    assert set(spec["properties"]) == set(listing.data)
    assert spec["properties"]["count"]["type"] == "integer"
    check_object(schema, spec["properties"]["results"]["items"], listing.data["results"][0])
    assert (
        authenticated.post(
            f"/api/v1/encounters/{encounter.id}/capture", {"success": True}, format="json"
        ).status_code
        == 400
    )


@pytest.mark.parametrize("label", ["encounters/captureresult", "collection/collectionentry"])
def test_capture_admin_readonly(client, user, encounter, label):
    result = capture_encounter(user=user, encounter_id=encounter.pk)
    obj = result if label.endswith("captureresult") else CollectionEntry.objects.get()
    user.is_staff = True
    user.save()
    client.force_login(user)
    root = f"/admin/{label}/"
    assert client.get(root).status_code == 403
    codename = "view_captureresult" if label.endswith("captureresult") else "view_collectionentry"
    user.user_permissions.add(Permission.objects.get(codename=codename))
    assert client.get(root).status_code == 200
    assert client.get(f"{root}{obj.pk}/change/").status_code == 200
    user.is_superuser = True
    user.save()
    assert client.get(f"{root}add/").status_code == 403
    assert client.post(f"{root}{obj.pk}/change/", {}).status_code == 403
    assert client.post(f"{root}{obj.pk}/delete/", {"post": "yes"}).status_code == 403
    request = RequestFactory().get(root)
    request.user = user
    assert admin.site._registry[type(obj)].get_actions(request) == {}
    assert CaptureResult.objects.count() == CollectionEntry.objects.count() == 1


def test_captured_admin_status_and_links(user, encounter):
    result = capture_encounter(user=user, encounter_id=encounter.pk)
    encounter.refresh_from_db()
    model_admin = admin.site._registry[Encounter]
    request = RequestFactory().get("/admin/")
    filter_ = EffectiveStatusFilter(
        request, {"effective_status": ["captured"]}, Encounter, model_admin
    )
    assert filter_.queryset(request, Encounter.objects.all()).count() == 1
    assert str(result.pk) in model_admin.capture_link(encounter)
    assert model_admin.effective_state(encounter) == "captured"
