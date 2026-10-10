from uuid import UUID, uuid4

from django.db import transaction

from .models import Source
from .services import require_source
from .tasks import collect_news_source, task_log


class EnqueueError(Exception):
    pass


def enqueue_collection(source_id):
    source_id = str(UUID(str(source_id)))
    source = Source.objects.get(pk=source_id)
    require_source(source)
    task_id = str(uuid4())

    def publish():
        try:
            collect_news_source.apply_async(
                args=[source_id],
                task_id=task_id,
                retry=False,
            )
        except Exception:
            task_log("publish_failed", task_id, source_id)
            raise EnqueueError("broker_publish_failed") from None
        task_log("published", task_id, source_id)

    transaction.on_commit(publish)
    # Inside an atomic block this is a reserved ID, not a publish receipt.
    return task_id
