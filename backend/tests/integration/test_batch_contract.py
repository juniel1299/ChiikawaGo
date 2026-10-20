from uuid import uuid4

import pytest
from drf_spectacular.generators import SchemaGenerator

from apps.batch.models import BatchJob

pytestmark = pytest.mark.django_db


def resolve(schema, value):
    if "$ref" in value:
        return schema["components"]["schemas"][value["$ref"].split("/")[-1]]
    if "allOf" in value:
        return resolve(schema, value["allOf"][0])
    return value


def check(schema, contract, data):
    contract = resolve(schema, contract)
    assert set(contract.get("required", [])) <= set(data)
    assert set(contract["properties"]) == set(data)
    for key, value in data.items():
        field = resolve(schema, contract["properties"][key])
        if value is None:
            assert field.get("nullable") or field.get("readOnly")
            continue
        kind = field.get("type")
        assert kind is not None, key
        assert isinstance(
            value,
            {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}[kind],
        ), key


def test_real_success_responses_match_schema(client, moderator):
    client.force_authenticate(moderator)
    job = BatchJob.objects.create(code="expired_token_cleanup", name="Cleanup", enabled=True)
    schema = SchemaGenerator().get_schema(public=True)
    response = client.post(
        f"/api/v1/batch/jobs/{job.pk}/runs", {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())
    )
    assert response.status_code == 202
    contract = schema["paths"]["/api/v1/batch/jobs/{id}/runs"]["post"]["responses"]["202"][
        "content"
    ]["application/json"]["schema"]
    check(schema, contract, response.json())
    listing = client.get("/api/v1/batch/executions")
    contract = schema["paths"]["/api/v1/batch/executions"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    check(schema, contract, listing.json())
    assert "409" in schema["paths"]["/api/v1/batch/jobs/{id}/runs"]["post"]["responses"]


def test_list_query_count_constant(client, moderator, django_assert_num_queries):
    from apps.batch import services
    from apps.batch.registry import Outcome

    client.force_authenticate(moderator)
    job = BatchJob.objects.create(code="expired_token_cleanup", name="Cleanup", enabled=True)
    for _ in range(3):
        row, _ = services.request_run(job_id=job.pk, key=uuid4(), sync=True)
        services.finish_attempt(row.pk, 1, Outcome({}))
    with django_assert_num_queries(2):
        response = client.get("/api/v1/batch/executions")
    assert response.status_code == 200 and response.json()["count"] == 3
