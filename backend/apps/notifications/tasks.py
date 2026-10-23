from uuid import UUID

from celery import shared_task

from .delivery import execute


@shared_task(
    name="notifications.deliver",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=False,
    soft_time_limit=90,
    time_limit=120,
)
def deliver(delivery_id, attempt):
    try:
        delivery_id = UUID(delivery_id)
        if type(attempt) is not int or not 1 <= attempt <= 3:
            raise ValueError()
        execute(delivery_id, attempt)
    except Exception:
        # SENDING intent remains recoverable as UNKNOWN; no raw provider/DB error escapes Celery.
        raise RuntimeError("push_execution_unconfirmed") from None
