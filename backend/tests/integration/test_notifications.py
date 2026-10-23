import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.notifications import delivery, services
from apps.notifications.models import PushDelivery, PushDevice, PushMessage
from apps.notifications.provider import Outcome

pytestmark = pytest.mark.django_db
SECRET = "a" * 43


def payload(version=0, **kw):
    return {
        "installation_secret": SECRET,
        "binding_version": version,
        "platform": "ios",
        "provider_token": "synthetic-token",
        "enabled": True,
        "permission_state": "authorized",
        **kw,
    }


def device(user, **kw):
    return services.register(user=user, installation_id=uuid.uuid4(), **payload(**kw))[0]


def message(moderator, user):
    return services.request_test(operator=moderator, target_user_id=user.pk, key=uuid.uuid4())


def test_registration_contract_rotation_and_cas(authenticated, user, other_user):
    installation = uuid.uuid4()
    url = f"/api/v1/notifications/devices/{installation}"
    response = authenticated.put(url, payload(), format="json")
    assert response.status_code == 201
    assert set(response.data) == {"installation_id", "binding_version", "enabled"}
    assert SECRET not in str(response.data) and "synthetic-token" not in str(response.data)
    assert authenticated.put(url, payload(), format="json").status_code == 409
    assert (
        authenticated.post(url + "/resolve", {"installation_secret": SECRET}, format="json").data[
            "binding_version"
        ]
        == 1
    )
    authenticated.force_authenticate(other_user)
    assert (
        authenticated.put(url, payload(1, provider_token="new-token"), format="json").status_code
        == 200
    )
    d = PushDevice.objects.get(installation_id=installation)
    assert d.user == other_user and d.binding_version == 2
    authenticated.force_authenticate(user)
    assert (
        authenticated.delete(
            url, {"installation_secret": SECRET, "binding_version": 1}, format="json"
        ).status_code
        == 409
    )
    assert (
        authenticated.delete(
            url, {"installation_secret": SECRET, "binding_version": 2}, format="json"
        ).status_code
        == 403
    )
    authenticated.force_authenticate(other_user)
    assert (
        authenticated.delete(
            url, {"installation_secret": SECRET, "binding_version": 2}, format="json"
        ).status_code
        == 204
    )
    d.refresh_from_db()
    assert not d.enabled and d.binding_version == 3 and not d.provider_token


def test_proof_and_permissions(client, authenticated, user):
    d = device(user)
    url = f"/api/v1/notifications/devices/{d.installation_id}"
    assert (
        authenticated.post(
            url + "/resolve", {"installation_secret": "b" * 43}, format="json"
        ).status_code
        == 403
    )
    assert authenticated.put(url, payload(1, latitude=37), format="json").status_code == 400
    authenticated.force_authenticate(None)
    assert client.put(url, payload(), format="json").status_code == 401


def test_disabled_registration_and_token_unique(user, other_user):
    device(user)
    with pytest.raises(services.Conflict):
        device(other_user)
    d = device(other_user, enabled=False, permission_state="denied")
    assert not d.provider_token


def test_multiple_deliveries_idempotency_and_rollback(
    user, moderator, django_capture_on_commit_callbacks
):
    device(user)
    device(user, provider_token="second-token")
    key = uuid.uuid4()
    with patch("apps.notifications.delivery.dispatch") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            m = services.request_test(operator=moderator, target_user_id=user.pk, key=key)
            assert not dispatch.called
        assert dispatch.call_count == 2
    assert services.request_test(operator=moderator, target_user_id=user.pk, key=key) == m
    assert m.deliveries.count() == 2
    with patch.object(PushDelivery.objects, "create", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError):
            message(moderator, user)
    assert PushMessage.objects.count() == 1


def test_operator_permission(user):
    with pytest.raises(PermissionDenied):
        services.request_test(operator=user, target_user_id=user.pk, key=uuid.uuid4())


def test_send_once_and_body_not_in_task(moderator, user):
    device(user)
    row = message(moderator, user).deliveries.get()
    with patch("apps.notifications.tasks.deliver.apply_async") as publish:
        assert delivery.dispatch(row.pk)
        args = publish.call_args.kwargs["args"]
        assert args == [str(row.pk), 1]
        assert "synthetic-token" not in str(publish.call_args)
    with patch(
        "apps.notifications.provider.send", return_value=Outcome(message_id="provider-id")
    ) as send:
        delivery.execute(row.pk, 1)
        delivery.execute(row.pk, 1)
        assert send.call_count == 1
    row.refresh_from_db()
    assert row.status == "SENT" and row.attempt == 1


@pytest.mark.parametrize(
    "outcome,status",
    [
        (Outcome(code="unregistered", unregistered=True), "FAILED"),
        (Outcome(code="invalid_payload_or_config"), "FAILED"),
        (Outcome(code="provider_transient", retryable=True), "RETRY_WAIT"),
    ],
)
def test_failure_classification(moderator, user, outcome, status):
    d = device(user)
    row = message(moderator, user).deliveries.get()
    with patch("apps.notifications.provider.send", return_value=outcome):
        delivery.execute(row.pk, 1)
    row.refresh_from_db()
    d.refresh_from_db()
    assert row.status == status
    assert d.enabled != outcome.unregistered


def test_retry_limit(moderator, user):
    device(user)
    row = message(moderator, user).deliveries.get()
    with patch(
        "apps.notifications.provider.send",
        return_value=Outcome(code="network_transient", retryable=True),
    ) as send:
        for attempt in range(1, 4):
            PushDelivery.objects.filter(pk=row.pk).update(
                next_attempt_at=timezone.now() - timedelta(seconds=1)
            )
            delivery.execute(row.pk, attempt)
        delivery.execute(row.pk, 4)
        assert send.call_count == 3
    row.refresh_from_db()
    assert row.status == "FAILED"


def test_rotation_during_send_does_not_disable_new_token(moderator, user):
    d = device(user)
    row = message(moderator, user).deliveries.get()

    def send(**kwargs):
        services.register(
            user=user, installation_id=d.installation_id, **payload(1, provider_token="rotated")
        )
        return Outcome(code="unregistered", unregistered=True)

    with patch("apps.notifications.provider.send", side_effect=send):
        delivery.execute(row.pk, 1)
    d.refresh_from_db()
    assert d.enabled and d.provider_token == "rotated"


def test_old_binding_skipped(moderator, user, other_user):
    d = device(user)
    row = message(moderator, user).deliveries.get()
    services.register(user=other_user, installation_id=d.installation_id, **payload(1))
    with patch("apps.notifications.provider.send") as send:
        delivery.execute(row.pk, 1)
        assert not send.called
    row.refresh_from_db()
    assert row.status == "SKIPPED"


def test_publish_failure_recovery(moderator, user):
    device(user)
    row = message(moderator, user).deliveries.get()
    with patch("apps.notifications.tasks.deliver.apply_async", side_effect=RuntimeError("secret")):
        assert not delivery.dispatch(row.pk)
    row.refresh_from_db()
    assert row.status == "PENDING" and row.failure_code == "publish_failed"
    assert "secret" not in row.safe_failure_message
    PushDelivery.objects.filter(pk=row.pk).update(
        next_dispatch_at=timezone.now() - timedelta(seconds=1)
    )
    with patch("apps.notifications.tasks.deliver.apply_async") as send:
        delivery.reconcile()
        assert send.call_count == 1


def test_provider_boundary_unknown_never_retried(moderator, user):
    device(user)
    row = message(moderator, user).deliveries.get()
    with patch("apps.notifications.provider.send", side_effect=RuntimeError("killed")):
        with pytest.raises(RuntimeError):
            delivery.execute(row.pk, 1)
    PushDelivery.objects.filter(pk=row.pk).update(started_at=timezone.now() - timedelta(minutes=10))
    with patch("apps.notifications.provider.send") as send:
        delivery.reconcile()
        delivery.execute(row.pk, 2)
        assert not send.called
    row.refresh_from_db()
    assert row.status == "UNKNOWN"


def test_constraints(user, moderator):
    d = device(user)
    row = message(moderator, user).deliveries.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        PushDelivery.objects.create(message=row.message, device=d, device_binding_version=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        PushDevice.objects.filter(pk=d.pk).update(binding_version=0)


def test_admin_readonly_token_hidden(client, moderator, user):
    d = device(user)
    client.force_login(moderator)
    response = client.get(reverse("admin:notifications_pushdevice_change", args=[d.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "synthetic-token" not in body and SECRET not in body and d.secret_hash not in body
    assert client.post(reverse("admin:notifications_pushdevice_add"), {}).status_code == 403
    assert client.get(reverse("admin:push_test_send")).status_code == 200


def test_registration_openapi_matches_response(authenticated):
    from drf_spectacular.generators import SchemaGenerator

    from tests.integration.test_encounter_contract import resolve

    schema = SchemaGenerator().get_schema(public=True)
    route = "/api/v1/notifications/devices/{installation_id}"
    response = authenticated.put(
        route.replace("{installation_id}", str(uuid.uuid4())), payload(), format="json"
    )
    assert response.status_code == 201
    body = resolve(
        schema,
        schema["paths"][route]["put"]["responses"]["201"]["content"]["application/json"]["schema"],
    )
    assert set(body["required"]) == set(body["properties"]) == set(response.data)
    assert body["properties"]["binding_version"]["type"] == "integer"
    assert isinstance(response.data["binding_version"], int)
    assert body["properties"]["enabled"]["type"] == "boolean"
    assert isinstance(response.data["enabled"], bool)
    assert body["properties"]["installation_id"]["type"] == "string"
    assert isinstance(response.data["installation_id"], str)
    assert "content" not in schema["paths"][route]["delete"]["responses"]["204"]


def test_admin_send_requires_csrf(moderator, user):
    from django.test import Client

    device(user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(moderator)
    url = reverse("admin:push_test_send")
    response = client.post(url, {"target_user": user.pk, "key": uuid.uuid4()})
    assert response.status_code == 403
    assert not PushMessage.objects.exists()
