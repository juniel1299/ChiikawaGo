import hashlib
import secrets

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from .models import PushDelivery, PushDevice, PushMessage


class Conflict(APIException):
    status_code = 409
    default_detail = "등록 상태가 변경되었습니다. 다시 확인해 주세요."
    default_code = "conflict"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def proof(device, secret):
    if not secrets.compare_digest(device.secret_hash, digest(secret)):
        raise PermissionDenied("기기 등록을 확인할 수 없습니다.")


def resolve(*, installation_id, secret):
    device = PushDevice.objects.filter(installation_id=installation_id).first()
    if device is None:
        raise NotFound()
    proof(device, secret)
    return device


def register(*, user, installation_id, installation_secret, binding_version, **data):
    now = timezone.now()
    try:
        with transaction.atomic():
            device = (
                PushDevice.objects.select_for_update(of=("self",), no_key=True)
                .filter(installation_id=installation_id)
                .first()
            )
            created = device is None
            if created:
                if binding_version != 0:
                    raise Conflict()
                device = PushDevice(
                    user=user,
                    installation_id=installation_id,
                    secret_hash=digest(installation_secret),
                )
            else:
                proof(device, installation_secret)
                if device.binding_version != binding_version:
                    raise Conflict()
                device.binding_version += 1
            device.user = user
            device.platform = data["platform"]
            device.permission_state = data["permission_state"]
            device.enabled = data["enabled"]
            device.provider_token = data["provider_token"] if device.enabled else ""
            device.token_hash = digest(device.provider_token) if device.enabled else ""
            device.last_registered_at = now
            device.save()
            return device, created
    except IntegrityError as exc:
        raise Conflict("기기 등록 충돌입니다. 현재 상태를 확인해 주세요.") from exc


@transaction.atomic
def unregister(*, user, installation_id, installation_secret, binding_version):
    device = (
        PushDevice.objects.select_for_update(of=("self",), no_key=True)
        .filter(installation_id=installation_id)
        .first()
    )
    if device is None:
        raise NotFound()
    proof(device, installation_secret)
    if device.binding_version != binding_version:
        raise Conflict()
    if device.user_id != user.pk:
        raise PermissionDenied()
    device.enabled = False
    device.provider_token = device.token_hash = ""
    device.binding_version += 1
    device.save()


def can_send(user):
    return user.is_active and user.is_staff and user.has_perm("notifications.send_operator_test")


@transaction.atomic
def request_test(*, operator, target_user_id, key):
    if not can_send(operator):
        raise PermissionDenied()
    # Serializes double-submit for one operator, never held over broker/provider I/O.
    get_user_model().objects.select_for_update(of=("self",), no_key=True).get(pk=operator.pk)
    existing = PushMessage.objects.filter(requested_by=operator, idempotency_key=key).first()
    if existing:
        if existing.target_user_id != target_user_id:
            raise Conflict("같은 키의 대상이 다릅니다.")
        return existing
    devices = list(
        PushDevice.objects.select_for_update(of=("self",), no_key=True)
        .filter(user_id=target_user_id, user__is_active=True, enabled=True)
        .order_by("id")
    )
    if not devices:
        raise Conflict("발송 가능한 기기가 없습니다.")
    message = PushMessage.objects.create(
        target_user_id=target_user_id, requested_by=operator, idempotency_key=key
    )
    for device in devices:
        delivery = PushDelivery.objects.create(
            message=message,
            device=device,
            device_binding_version=device.binding_version,
            next_dispatch_at=timezone.now(),
        )
        transaction.on_commit(lambda pk=delivery.pk: enqueue_safely(pk))
    return message


def enqueue_safely(pk):
    from .delivery import dispatch

    try:
        dispatch(pk)
    except Exception:
        # Durable PENDING intent is recovered by reconciliation. Never log broker credentials.
        return False
    return True
