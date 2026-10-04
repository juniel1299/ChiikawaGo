import io
import json
import logging

import pytest
from drf_spectacular.generators import SchemaGenerator

pytestmark = pytest.mark.django_db


def resolve(schema, obj):
    while "$ref" in obj:
        obj = schema["components"]["schemas"][obj["$ref"].split("/")[-1]]
    return obj


def test_encounter_openapi_matches_actual_responses(authenticated, spawn_rule):
    schema = SchemaGenerator().get_schema(public=True)
    path = "/api/v1/encounters"
    data = {"spot_id": str(spawn_rule.spot_id), "latitude": 37.5665, "longitude": 126.978}
    request = resolve(
        schema,
        schema["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"],
    )
    assert set(request["required"]) == set(data)
    first = authenticated.post(path, data)
    second = authenticated.post(path, data)
    detail = authenticated.get(f"{path}/{first.data['id']}")
    for response, route, method, status in [
        (first, path, "post", 201),
        (second, path, "post", 200),
        (detail, path + "/{id}", "get", 200),
    ]:
        assert response.status_code == status
        body = resolve(
            schema,
            schema["paths"][route][method]["responses"][str(status)]["content"]["application/json"][
                "schema"
            ],
        )
        assert set(body["properties"]) == set(response.data)
        assert set(body["required"]) == set(response.data)
        for key, value in response.data.items():
            field = body["properties"][key]
            if "allOf" in field:
                field = field["allOf"][0]
            field = resolve(schema, field)
            assert field["type"] == "string"
            assert isinstance(value, str)
    # A fresh user/spot pair must fail when no rule exists.
    from apps.encounters.models import Encounter

    Encounter.objects.all().delete()
    spawn_rule.is_active = False
    spawn_rule.save()
    error = authenticated.post(path, data)
    assert error.status_code == 409
    body = resolve(
        schema,
        schema["paths"][path]["post"]["responses"]["409"]["content"]["application/json"]["schema"],
    )
    assert set(body["required"]) == set(error.data)
    assert error.data["error"]["details"]["reason"] == "no_spawn_rule"


def test_encounter_request_logs_do_not_record_coordinates(authenticated, spawn_rule, monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(
        logging.getLogger("chii.requests"), "handlers", [logging.StreamHandler(stream)]
    )
    response = authenticated.post(
        "/api/v1/encounters",
        {
            "spot_id": str(spawn_rule.spot_id),
            "latitude": 37.566500123,
            "longitude": 126.978000123,
        },
        HTTP_AUTHORIZATION="Bearer private-encounter-token",
    )
    assert response.status_code == 201
    record = json.loads(stream.getvalue())
    assert record["request_id"] == response["X-Request-ID"]
    assert "37.566500123" not in stream.getvalue()
    assert "126.978000123" not in stream.getvalue()
    assert "private-encounter-token" not in stream.getvalue()
