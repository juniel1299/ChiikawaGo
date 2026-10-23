from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.test import override_settings
from firebase_admin import exceptions, messaging
from requests.exceptions import SSLError

from apps.notifications.provider import send


@override_settings(PUSH_ENABLED=True, FIREBASE_PROJECT_ID="synthetic")
@pytest.mark.parametrize(
    "error,code,retry,disable",
    [
        (messaging.UnregisteredError("private-token"), "unregistered", False, True),
        (exceptions.UnavailableError("private-token"), "provider_transient", True, False),
        (
            exceptions.InvalidArgumentError("private-token"),
            "invalid_payload_or_config",
            False,
            False,
        ),
        (SSLError("private-secret"), "provider_tls_error", False, False),
    ],
)
def test_provider_classification_and_no_sdk_retry(error, code, retry, disable):
    service = MagicMock()
    with (
        patch("firebase_admin.get_app"),
        patch("firebase_admin.messaging._get_messaging_service", return_value=service),
        patch("firebase_admin.messaging.send", side_effect=error) as deliver,
    ):
        result = send(
            token="synthetic-fid", message=SimpleNamespace(title="test", body="test", pk=1)
        )
    assert result.code == code and result.retryable == retry and result.unregistered == disable
    assert "private" not in repr(result)
    adapter = service._client.session.mount.call_args.args[1]
    assert adapter.max_retries.total == 0
    assert deliver.call_args.args[0].fid == "synthetic-fid"
    assert deliver.call_args.args[0].data["destination"] == "HOME"


@override_settings(PUSH_ENABLED=True)
def test_worker_timeout_leaves_uncertainty_to_reconciliation():
    with (
        patch("firebase_admin.get_app"),
        patch("firebase_admin.messaging._get_messaging_service"),
        patch("firebase_admin.messaging.send", side_effect=SoftTimeLimitExceeded()),
        pytest.raises(SoftTimeLimitExceeded),
    ):
        send(token="synthetic-fid", message=SimpleNamespace(title="test", body="test", pk=1))
