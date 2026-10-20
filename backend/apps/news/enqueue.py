from uuid import uuid4

from rest_framework.exceptions import ValidationError

from apps.batch.models import BatchJob
from apps.batch.services import request_run


def configured_job(source_id):
    job = BatchJob.objects.filter(code=BatchJob.Code.NEWS, source_id=source_id).first()
    if not job:
        raise ValidationError("Batch Job을 등록하고 Source를 연결하세요.")
    return job


def enqueue_collection(source_id):
    execution, _ = request_run(job_id=configured_job(source_id).pk, key=uuid4())
    return execution
