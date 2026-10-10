from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import BatchExecution
from .services import lock_execution


def dispatch(execution_id, now=None):
    from .tasks import execute

    now = now or timezone.now()
    with transaction.atomic():
        row = lock_execution(execution_id)
        if (
            row.status not in ["queued", "retry_wait"]
            or not row.celery_task_id
            or not row.next_dispatch_at
            or row.next_dispatch_at > now
        ):
            return False
        if row.next_attempt_at and row.next_attempt_at > now:
            return False
        attempt = row.attempt + 1
        reservation = row.publish_attempts + 1
        row.publish_attempts = reservation
        row.next_dispatch_at = now + timedelta(seconds=120)
        row.save()
        task_id = str(row.celery_task_id)
        policy = row.input_snapshot.copy()
    error = ""
    try:
        execute.apply_async(
            args=[str(execution_id), attempt],
            task_id=task_id,
            retries=attempt - 1,
            retry=False,
            soft_time_limit=policy["soft_limit"],
            time_limit=policy["hard_limit"],
        )
    except Exception:
        error = "broker_publish_failed"
    confirmed_at = timezone.now() if not error else None
    with transaction.atomic():
        row = lock_execution(execution_id)
        if row.publish_attempts == reservation:
            # A fast Worker may already have claimed/completed this attempt.
            # Preserve its state/retry deadline, but still record broker confirmation.
            if confirmed_at:
                row.last_published_at = confirmed_at
            if row.attempt == attempt - 1 and row.status in ["queued", "retry_wait"]:
                row.dispatch_error_code = error
                if error:
                    row.next_dispatch_at = now + timedelta(seconds=30)
            row.save()
    return not error


def reconcile(now=None):
    now = now or timezone.now()
    ids = BatchExecution.objects.filter(
        status__in=["queued", "retry_wait"], next_dispatch_at__lte=now, celery_task_id__isnull=False
    ).values_list("id", flat=True)
    for execution_id in list(ids):
        dispatch(execution_id, now)
