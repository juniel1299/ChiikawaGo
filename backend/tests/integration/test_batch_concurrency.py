from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone

from apps.batch import services
from apps.batch.models import BatchExecution, BatchJob, BatchSchedule
from apps.batch.registry import Outcome
from tests.integration.test_encounter_concurrency import run_overlapping

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def job(monkeypatch):
    monkeypatch.setattr(services, "_kick", lambda row: None)
    return BatchJob.objects.create(code="expired_token_cleanup", name="Cleanup", enabled=True)


def pause_job(monkeypatch):
    locked, release = Event(), Event()
    original = services.job_locked

    def pause(pk):
        row = original(pk)
        if not locked.is_set():
            locked.set()
            assert release.wait(10)
        return row

    monkeypatch.setattr(services, "job_locked", pause)
    return locked, release


def test_simultaneous_same_key_accepts_once(job, monkeypatch):
    locked, release = pause_job(monkeypatch)
    key = uuid4()

    def run():
        return services.request_run(job_id=job.pk, key=key)

    a, b = run_overlapping(run, run, locked, release)
    assert a[1] and not b[1] and a[0].pk == b[0].pk
    assert BatchExecution.objects.count() == 1


def test_simultaneous_worker_claim_once(job, monkeypatch):
    row, _ = services.request_run(job_id=job.pk, key=uuid4())
    locked, release = pause_job(monkeypatch)
    a, b = run_overlapping(
        lambda: services.claim(row.pk, 1, "a"),
        lambda: services.claim(row.pk, 1, "b"),
        locked,
        release,
    )
    assert a is not None and b is None


def test_simultaneous_operator_retry_once(job, moderator, monkeypatch):
    row, _ = services.request_run(job_id=job.pk, key=uuid4())
    services.claim(row.pk, 1, "w")
    services.finish_attempt(row.pk, 1, Outcome({}, ({"code": "error", "stage": "execution"},)))
    locked, release = pause_job(monkeypatch)

    def run():
        return services.request_run(job_id=job.pk, key=uuid4(), user=moderator, retry_of=row.pk)

    a, b = run_overlapping(run, run, locked, release)
    assert a[1] and not b[1] and a[0].pk == b[0].pk


def test_scheduler_skips_locked_job_then_coalesces(job):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections, connection

    now = timezone.now().replace(second=0, microsecond=0)
    BatchSchedule.objects.create(
        job=job,
        cron_expression="* * * * *",
        timezone="UTC",
        enabled=True,
        next_run_at=now - timedelta(days=1),
    )

    def tick():
        close_old_connections()
        try:
            return services.schedule_due(job.pk, now)
        finally:
            connection.close()

    with transaction.atomic(), ThreadPoolExecutor(max_workers=1) as pool:
        BatchJob.objects.select_for_update().get(pk=job.pk)
        assert pool.submit(tick).result(timeout=5) is None
    assert services.schedule_due(job.pk, now).scheduled_for == now
    assert services.schedule_due(job.pk, now) is None


def test_accept_rollback_leaves_no_execution(job, monkeypatch):
    original = BatchExecution.save

    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("injected")

    monkeypatch.setattr(BatchExecution, "save", fail)
    with pytest.raises(RuntimeError):
        services.request_run(job_id=job.pk, key=uuid4())
    assert not BatchExecution.objects.exists()
