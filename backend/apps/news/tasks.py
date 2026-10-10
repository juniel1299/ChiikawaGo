import json
import logging

logger = logging.getLogger("chii.tasks")


def task_log(event, task_id, source_id, **fields):
    logger.info(json.dumps({"event": event, "task_id": task_id, "source_id": source_id, **fields}))
