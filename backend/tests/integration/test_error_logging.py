import io
import json
import logging

import pytest
from django.db import OperationalError
from psycopg.errors import DeadlockDetected

from apps.accounts.views import RegisterView

pytestmark = pytest.mark.django_db
SECRETS = [
    "Secret-password-42!",
    "private-jwt-value",
    "private-refresh-value",
    "Bearer private-authorization",
    "private-full-body",
    "37.123456789",
    "127.987654321",
    "SELECT private_column WHERE secret = 'private-sql-parameter'",
]


@pytest.mark.parametrize("database_error", [False, True])
def test_internal_error_logs_safe_trace_and_request_id(client, monkeypatch, database_error):
    stream = io.StringIO()
    logger = logging.getLogger("chii.errors")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    monkeypatch.setattr(logger, "handlers", [handler])

    def failing_create(self, serializer):
        sensitive_message = " ".join(SECRETS)
        try:
            error = (
                DeadlockDetected(sensitive_message)
                if database_error
                else ValueError(sensitive_message)
            )
            error.add_note(sensitive_message)
            raise error
        except Exception as cause:
            raise OperationalError(sensitive_message) from cause

    monkeypatch.setattr(RegisterView, "perform_create", failing_create)
    response = client.post(
        "/api/v1/auth/register?latitude=37.123456789&longitude=127.987654321",
        {
            "email": "new@example.com",
            "display_name": "private-full-body",
            "password": SECRETS[0],
            "refresh": SECRETS[2],
        },
        format="json",
        HTTP_AUTHORIZATION=SECRETS[3],
    )
    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "서버 오류가 발생했습니다.",
        "details": {},
    }
    output = stream.getvalue()
    record = json.loads(output)
    assert record["request_id"] == response["X-Request-ID"] == response.json()["request_id"]
    assert record["exception_type"] == "OperationalError"
    assert record["exception_message"] == "Internal exception; original message withheld"
    assert any(frame["function"] == "failing_create" for frame in record["stack_trace"])
    for frame in record["stack_trace"]:
        assert set(frame) == {"file", "function", "line"}
        assert isinstance(frame["line"], int)
    cause = record["chained_exceptions"][0]
    assert cause["exception_type"] == ("DeadlockDetected" if database_error else "ValueError")
    assert cause["exception_message"] == (
        "Database deadlock detected"
        if database_error
        else "Internal exception; original message withheld"
    )
    assert cause["stack_trace"]
    for secret in SECRETS:
        assert secret not in output
        assert secret not in response.content.decode()
    for internal in ("OperationalError", "stack_trace", "failing_create"):
        assert internal not in response.content.decode()


def test_django_server_error_uses_safe_logging(monkeypatch):
    from django.test import RequestFactory

    from config.api import server_error

    stream = io.StringIO()
    monkeypatch.setattr(
        logging.getLogger("chii.errors"), "handlers", [logging.StreamHandler(stream)]
    )
    request = RequestFactory().get("/admin/")
    request.request_id = "server-error-request-id"
    try:
        raise RuntimeError(" ".join(SECRETS))
    except RuntimeError:
        response = server_error(request)
    record = json.loads(stream.getvalue())
    assert response.status_code == 500
    assert record["request_id"] == json.loads(response.content)["request_id"] == request.request_id
    assert record["exception_type"] == "RuntimeError"
    assert record["exception_message"] == "Internal exception; original message withheld"
    assert record["stack_trace"][0]["function"] == "test_django_server_error_uses_safe_logging"
    for secret in SECRETS:
        assert secret not in stream.getvalue()
        assert secret not in response.content.decode()
