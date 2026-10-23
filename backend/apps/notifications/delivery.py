import secrets
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import provider
from .models import PushDelivery, PushDevice

WAITING = [PushDelivery.Status.PENDING, PushDelivery.Status.RETRY_WAIT]


def locked(pk):
    device_id = PushDelivery.objects.values_list("device_id", flat=True).get(pk=pk)
    device = PushDevice.objects.select_for_update(of=("self",), no_key=True).get(pk=device_id)
    row = (
        PushDelivery.objects.select_for_update(of=("self",), no_key=True)
        .select_related("message")
        .get(pk=pk)
    )
    return device, row


def dispatch(pk):
    from .tasks import deliver

    now = timezone.now()
    with transaction.atomic():
        _, row = locked(pk)
        if row.status not in WAITING or row.next_dispatch_at is None or row.next_dispatch_at > now:
            return False
        if row.next_attempt_at and row.next_attempt_at > now:
            return False
        row.next_dispatch_at = now + timedelta(seconds=120)
        row.celery_task_id = uuid.uuid4()
        row.save()
        attempt, task_id = row.attempt + 1, str(row.celery_task_id)
    try:
        deliver.apply_async(args=[str(pk), attempt], task_id=task_id)
    except Exception:
        with transaction.atomic():
            _, row = locked(pk)
            if row.status in WAITING and str(row.celery_task_id) == task_id:
                row.next_dispatch_at = timezone.now() + timedelta(seconds=30)
                row.failure_code = "publish_failed"
                row.save()
        return False
    with transaction.atomic():
        _, row = locked(pk)
        row.last_published_at = timezone.now()
        row.save(update_fields=["last_published_at"])
    return True


def execute(pk, attempt):
    with transaction.atomic():
        device, row = locked(pk)
        now = timezone.now()
        if (
            row.status not in WAITING
            or row.attempt + 1 != attempt
            or (row.next_attempt_at and row.next_attempt_at > now)
        ):
            return
        if (
            not device.enabled
            or device.user_id != row.message.target_user_id
            or device.binding_version != row.device_binding_version
            or not device.user.is_active
        ):
            row.status = PushDelivery.Status.SKIPPED
            row.failure_code = "binding_changed_or_disabled"
            row.finished_at = now
            row.next_dispatch_at = None
            row.save()
            return
        row.status = PushDelivery.Status.SENDING
        row.attempt = attempt
        row.started_at = now
        row.next_dispatch_at = None
        row.save()
        token, token_hash, message = device.provider_token, device.token_hash, row.message
    # Persist the uncertainty boundary before any external provider call.
    with transaction.atomic():
        device, current = locked(pk)
        if current.status != PushDelivery.Status.SENDING or current.attempt != attempt:
            return
        if (
            not device.enabled
            or device.binding_version != current.device_binding_version
            or device.user_id != current.message.target_user_id
            or not device.user.is_active
        ):
            current.status = PushDelivery.Status.SKIPPED
            current.failure_code = "binding_changed_or_disabled"
            current.finished_at = timezone.now()
            current.save()
            return
        current.provider_started_at = timezone.now()
        current.save(update_fields=["provider_started_at"])
    outcome = provider.send(token=token, message=message)
    with transaction.atomic():
        device, row = locked(pk)
        if row.status != PushDelivery.Status.SENDING or row.attempt != attempt:
            return
        now = timezone.now()
        row.failure_code = outcome.code
        row.safe_failure_message = "발송을 완료하지 못했습니다." if outcome.code else ""
        if not outcome.code:
            row.status = PushDelivery.Status.SENT
            row.provider_message_id = outcome.message_id[:256]
            row.finished_at = now
        elif outcome.retryable and attempt < 3:
            row.status = PushDelivery.Status.RETRY_WAIT
            delay = max(outcome.retry_after, 60 * attempt + secrets.randbelow(31))
            row.next_attempt_at = now + timedelta(seconds=delay)
            row.next_dispatch_at = row.next_attempt_at
            row.provider_started_at = None
        else:
            row.status = PushDelivery.Status.FAILED
            row.finished_at = now
        if (
            outcome.unregistered
            and device.binding_version == row.device_binding_version
            and device.token_hash == token_hash
        ):
            device.enabled = False
            device.provider_token = device.token_hash = ""
            device.binding_version += 1
            device.save()
        row.save()


def reconcile(now=None):
    now = now or timezone.now()
    for pk in PushDelivery.objects.filter(
        status__in=WAITING, next_dispatch_at__lte=now
    ).values_list("pk", flat=True)[:100]:
        dispatch(pk)
    # Longer than task hard limit. Never retry a possibly accepted send.
    stale = PushDelivery.objects.filter(
        status="SENDING", started_at__lte=now - timedelta(seconds=240)
    )
    for pk in list(stale.values_list("pk", flat=True)[:100]):
        with transaction.atomic():
            _, row = locked(pk)
            if row.status != "SENDING" or row.started_at > now - timedelta(seconds=240):
                continue
            row.status = "UNKNOWN" if row.provider_started_at else "FAILED"
            row.failure_code = (
                "provider_outcome_unknown" if row.provider_started_at else "worker_lost_before_send"
            )
            row.safe_failure_message = "자동 재시도하지 않습니다. 운영 확인이 필요합니다."
            row.finished_at = now
            row.save()
