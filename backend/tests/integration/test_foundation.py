from unittest.mock import patch

import pytest
from django.db import OperationalError
from drf_spectacular.generators import SchemaGenerator


@pytest.mark.django_db
def test_health_readiness_and_error_contract(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    with patch("config.health.connection.cursor", side_effect=OperationalError("private db info")):
        response = client.get("/ready")
    assert response.status_code == 503
    assert b"private" not in response.content
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["request_id"] == response["X-Request-ID"]
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.data["error"]["code"] == "authentication_failed"


def test_openapi_includes_core_endpoints():
    schema = SchemaGenerator().get_schema(public=True)
    assert "/api/v1/auth/token" in schema["paths"]
    params = schema["paths"]["/api/v1/spots/nearby"]["get"]["parameters"]
    assert {"latitude", "longitude", "radius_m"} <= {param["name"] for param in params}


def test_request_log_does_not_include_query_or_credentials(client, caplog):
    with caplog.at_level("INFO", logger="chii.requests"):
        with patch("config.middleware.logger.info") as log:
            client.get("/health?latitude=37.123456", HTTP_AUTHORIZATION="Bearer secret-token")
    message = log.call_args.args[0]
    assert "37.123456" not in message
    assert "secret-token" not in message
    assert "request_id" in message
