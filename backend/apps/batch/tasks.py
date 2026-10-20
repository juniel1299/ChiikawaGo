from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

from celery import shared_task
from celery.exceptions import Retry
from django.db import transaction
from django.utils import timezone

from apps.news.tasks import task_log
from config.error_logging import log_internal_exception

from . import services


class BatchTaskError(Exception):
    pass


@shared_task(
    bind=True,
    name="batch.execute",
    ignore_result=True,
    max_retries=2,
    acks_late=True,
    acks_on_failure_or_timeout=True,
    reject_on_worker_lost=False,
    soft_time_limit=600,
    time_limit=660,
)
def execute(self, execution_id, attempt):
    try:
        execution_id = str(UUID(execution_id))
        if type(attempt) is not int or not 1 <= attempt <= 3:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise BatchTaskError("invalid_payload") from None
    try:
        execution = services.claim(execution_id, attempt, self.request.hostname or "worker")
        if not execution:
            task_log(
                "duplicate_ignored",
                self.request.id,
                None,
                execution_id=execution_id,
                attempt=attempt,
            )
            return None
        task_log(
            "started",
            self.request.id,
            execution.input_snapshot["source_id"],
            execution_id=execution_id,
            attempt=attempt,
        )
        outcome = services.run_attempt(execution)
        row = services.finish_attempt(execution_id, attempt, outcome)
        if row.status == "retry_wait":
            delay = max(0, (row.next_attempt_at - timezone.now()).total_seconds())
            try:
                retry_signal = self.retry(
                    args=[execution_id, attempt + 1],
                    countdown=delay,
                    exc=BatchTaskError("transient_failure"),
                    throw=False,
                )
            except Exception:
                # The DB remains authoritative; the scheduler recovers a lost retry.
                with transaction.atomic():
                    current = services.lock_execution(execution_id)
                    if current.status == "retry_wait" and current.attempt == attempt:
                        current.dispatch_error_code = "retry_publish_failed"
                        current.next_dispatch_at = current.next_attempt_at + timedelta(seconds=30)
                        current.save()
                raise BatchTaskError("retry_publish_failed") from None
            task_log(
                "retry",
                self.request.id,
                row.input_snapshot["source_id"],
                execution_id=execution_id,
                attempt=attempt,
                delay_s=delay,
            )
            raise retry_signal
        if row.status == "failed":
            task_log(
                "failed",
                self.request.id,
                row.input_snapshot["source_id"],
                execution_id=execution_id,
                attempt=attempt,
                code=row.failure_code,
            )
            raise BatchTaskError(row.failure_code)
        task_log(
            "succeeded",
            self.request.id,
            row.input_snapshot["source_id"],
            execution_id=execution_id,
            attempt=attempt,
            **outcome.counts,
        )
        return outcome.counts
    except (Retry, BatchTaskError):
        raise
    except Exception as exc:
        log_internal_exception(exc, SimpleNamespace(request_id=execution_id))
        # A failed final DB write must not be presented as a completed execution.
        raise BatchTaskError("execution_state_unconfirmed") from None
