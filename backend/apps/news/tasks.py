import json
import logging
import random
from time import monotonic
from types import SimpleNamespace
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from celery.exceptions import Retry

from config.error_logging import log_internal_exception

from . import crawler

logger = logging.getLogger("chii.tasks")


class CollectionTaskError(Exception):
    """Only fixed error codes reach Celery logs/events."""


def task_log(event, task_id, source_id, **fields):
    logger.info(json.dumps({"event": event, "task_id": task_id, "source_id": source_id, **fields}))


@shared_task(
    bind=True,
    name="news.collect_news_source",
    ignore_result=True,
    max_retries=2,
    acks_late=True,
    acks_on_failure_or_timeout=True,
    reject_on_worker_lost=False,
    soft_time_limit=600,
    time_limit=660,
)
def collect_news_source(self, source_id):
    started = monotonic()
    # Never echo malformed payloads into logs or errors.
    try:
        source_id = str(UUID(source_id))
    except (ValueError, TypeError, AttributeError):
        task_log("failed", self.request.id, None, code="invalid_source_id")
        raise CollectionTaskError("invalid_source_id") from None
    attempt = self.request.retries + 1
    task_log("started", self.request.id, source_id, attempt=attempt)
    try:
        result = crawler.collect(source_id)
    except SoftTimeLimitExceeded:
        task_log("failed", self.request.id, source_id, attempt=attempt, code="time_limit")
        raise CollectionTaskError("time_limit") from None
    except Exception as exc:
        log_internal_exception(exc, SimpleNamespace(request_id=self.request.id))
        task_log("failed", self.request.id, source_id, attempt=attempt, code="internal_error")
        raise CollectionTaskError("internal_error") from None
    fields = {
        "attempt": attempt,
        "duration_s": round(monotonic() - started, 3),
        **result.counts,
        "errors": [{"code": error.code, "stage": error.stage} for error in result.errors],
    }
    if not result.errors:
        task_log("succeeded", self.request.id, source_id, **fields)
        return result.counts
    if result.retryable and self.request.retries < self.max_retries:
        delay = random.uniform(0, min(60 * 2**self.request.retries, 120))
        task_log("retry", self.request.id, source_id, delay_s=delay, **fields)
        try:
            raise self.retry(
                exc=CollectionTaskError("transient_collection_failure"), countdown=delay
            )
        except Retry:
            raise
        except Exception:
            task_log("failed", self.request.id, source_id, code="retry_publish_failed")
            raise CollectionTaskError("retry_publish_failed") from None
    task_log("failed", self.request.id, source_id, **fields)
    raise CollectionTaskError("retry_exhausted" if result.retryable else "collection_failed")
