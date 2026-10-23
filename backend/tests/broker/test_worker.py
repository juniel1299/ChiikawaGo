import json
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from celery import Celery
from django.conf import settings
from django.db import connection
from django.utils import timezone
from kombu import Queue

from apps.batch import services
from apps.batch.models import BatchExecution, BatchJob
from apps.news.models import NewsCandidate, RawItem

pytestmark = [pytest.mark.broker, pytest.mark.django_db(transaction=True)]


def wait_for(check, diagnostic, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.025)
    pytest.fail("Timed out waiting for worker observation:\n" + diagnostic())


@pytest.fixture
def worker(tmp_path):
    instances = []
    sender = Celery("test_sender", broker=settings.CELERY_BROKER_URL)
    queue = "test.news." + uuid4().hex
    sender.conf.update(
        task_queues=[Queue(queue, exchange=queue, routing_key=queue, durable=True)],
        task_default_queue=queue,
        task_default_exchange=queue,
        task_default_routing_key=queue,
        task_serializer="json",
        task_ignore_result=True,
        task_publish_retry=False,
        broker_transport_options={"confirm_publish": True},
    )

    class Worker:
        def __init__(self):
            self.proc = None
            self.queue = queue
            self.log = tmp_path / "worker.log"
            self.control = tmp_path

        def output(self):
            return self.log.read_text() if self.log.exists() else ""

        def start(self, mode="normal"):
            env = os.environ.copy()
            env.update(
                POSTGRES_DB=connection.settings_dict["NAME"],
                DJANGO_SETTINGS_MODULE="config.settings.test",
                BROKER_TEST_QUEUE=queue,
                BROKER_TEST_CONTROL=str(tmp_path),
                BROKER_TEST_MODE=mode,
            )
            ready_before = self.output().count("ready.")
            output = self.log.open("a")
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "tests.broker.worker"],
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            output.close()
            instances.append(self.proc)
            wait_for(lambda: self.output().count("ready.") > ready_before, self.output)
            return self

        def send(self, execution=None, retry_of=None):
            job, _ = BatchJob.objects.get_or_create(
                code="news_collection",
                defaults={"name": "News", "enabled": True, "source": self.source},
            )
            if execution is None:
                with patch.object(services, "_kick"):
                    execution, _ = services.request_run(
                        job_id=job.pk, key=uuid4(), retry_of=retry_of
                    )
            self.execution = execution
            return sender.send_task(
                "batch.execute",
                args=[str(execution.pk), execution.attempt + 1],
                task_id=str(execution.celery_task_id),
                queue=queue,
                ignore_result=True,
            ).id

        def send_push(self, delivery, attempt=1):
            return sender.send_task(
                "notifications.deliver", args=[str(delivery.pk), attempt], queue=queue
            ).id

        def recover(self, user):
            BatchExecution.objects.filter(pk=self.execution.pk).update(
                attempt_started_at=timezone.now() - timedelta(seconds=781)
            )
            return services.confirm_failure(self.execution.pk, user, worker_stopped=True)

        def publish(self, **kwargs):
            return sender.send_task("batch.execute", queue=queue, **kwargs)

        def event(self, task_id, event):
            def find():
                for line in self.output().splitlines():
                    if "{" not in line:
                        continue
                    try:
                        record = json.loads(line[line.index("{") :])
                    except ValueError:
                        continue
                    if record.get("task_id") == task_id and record.get("event") == event:
                        return record
                return None

            return wait_for(find, self.output)

        def kill(self):
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=10)

    running = Worker()
    try:
        yield running
    finally:
        for proc in instances:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
        with sender.connection_for_write() as conn:
            channel = conn.channel()
            channel.queue_delete(queue=queue)
            channel.exchange_delete(exchange=queue)
        sender.close()


def test_real_broker_duplicate_execution(worker, news_source):
    worker.source = news_source
    worker.start()
    first = worker.send()
    second = worker.send(execution=worker.execution)
    assert worker.event(first, "succeeded")["created"] == 1
    worker.event(second, "duplicate_ignored")
    assert NewsCandidate.objects.count() == RawItem.objects.count() == 1
    assert f"batch.execute[{first}] received" in worker.output()


@pytest.mark.parametrize(
    "mode,attempts,event",
    [("transient", 2, "succeeded"), ("exhaust", 3, "failed"), ("forbidden", 1, "failed")],
)
def test_real_retry_and_terminal_failure(worker, news_source, mode, attempts, event):
    worker.source = news_source
    worker.start(mode)
    task_id = worker.send()
    assert worker.event(task_id, event)["attempt"] == attempts
    if attempts > 1:
        assert worker.event(task_id, "retry")["attempt"] == 1
    else:
        assert '"event": "retry"' not in worker.output()
    assert NewsCandidate.objects.count() == (1 if mode == "transient" else 0)


def test_worker_save_failure_rolls_back_and_manual_retry(worker, news_source):
    worker.source = news_source
    worker.start("rollback")
    worker.event(worker.send(), "failed")
    assert not RawItem.objects.exists() and not NewsCandidate.objects.exists()
    worker.event(worker.send(retry_of=worker.execution.pk), "succeeded")
    assert NewsCandidate.objects.count() == 1


def test_whole_worker_loss_requires_operator_recovery(worker, news_source, moderator):
    worker.source = news_source
    worker.start("pause")
    task_id = worker.send()
    wait_for(lambda: (worker.control / "paused").exists(), worker.output)
    assert NewsCandidate.objects.count() == 1
    worker.kill()
    worker.start("pause")
    worker.event(task_id, "duplicate_ignored")
    worker.execution.refresh_from_db()
    assert worker.execution.status == "running"
    worker.recover(moderator)
    worker.event(worker.send(retry_of=worker.execution.pk), "succeeded")
    assert NewsCandidate.objects.count() == 2


def test_child_loss_is_acked_and_operator_retry_is_safe(worker, news_source, moderator):
    worker.source = news_source
    worker.start("kill_child")
    first = worker.send()
    wait_for(lambda: "WorkerLostError" in worker.output(), worker.output)
    assert NewsCandidate.objects.count() == 1
    worker.recover(moderator)
    second = worker.send(retry_of=worker.execution.pk)
    worker.event(second, "succeeded")
    assert NewsCandidate.objects.count() == 2
    assert worker.output().count(f"batch.execute[{first}] received") == 1


def test_non_json_is_rejected(worker, news_source):
    from kombu import Producer

    worker.source = news_source
    worker.start()
    with Celery(broker=settings.CELERY_BROKER_URL).connection_for_write() as conn:
        # Harmless bytes tagged as pickle: rejection must precede deserialization.
        Producer(conn).publish(
            b"not a pickle",
            exchange=worker.queue,
            routing_key=worker.queue,
            content_type="application/x-python-serialize",
            content_encoding="binary",
            headers={"task": "batch.execute", "id": str(uuid4())},
        )
    wait_for(lambda: "ContentDisallowed" in worker.output(), worker.output)
    assert not NewsCandidate.objects.exists()
    worker.event(worker.send(), "succeeded")


@pytest.mark.parametrize(
    "mode,terminal,expected",
    [
        ("normal", "succeeded", {"task-received", "task-started", "task-succeeded"}),
        ("transient", "succeeded", {"task-retried", "task-succeeded"}),
        ("forbidden", "failed", {"task-failed"}),
    ],
)
def test_actual_task_events(worker, news_source, mode, terminal, expected):
    from functools import partial

    from kombu import Consumer

    worker.source = news_source
    worker.start(mode)
    observer = Celery("test_observer", broker=settings.CELERY_BROKER_URL)
    events = []
    try:
        with observer.connection_for_read() as conn:
            receiver = observer.events.Receiver(
                conn, handlers={"*": events.append}, queue_exclusive=True
            )
            channel = conn.channel()
            consumer = receiver.get_consumers(partial(Consumer, channel), channel)[0]
            with consumer:
                task_id = worker.send()
                worker.event(task_id, terminal)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    observed = {e["type"] for e in events if e.get("uuid") == task_id}
                    if expected <= observed:
                        break
                    try:
                        conn.drain_events(timeout=0.25)
                    except TimeoutError:
                        pass
                assert expected <= observed
    finally:
        observer.close()


def test_api_acceptance_survives_broker_failure_and_reconciliation(
    worker, news_source, moderator, client, monkeypatch
):
    from apps.batch import delivery, tasks

    worker.source = news_source
    worker.start()
    job = BatchJob.objects.create(
        code="news_collection", name="News", source=news_source, enabled=True
    )
    client.force_authenticate(moderator)

    def unavailable(**kwargs):
        raise OSError("private broker failure")

    monkeypatch.setattr(tasks.execute, "apply_async", unavailable)
    response = client.post(
        f"/api/v1/batch/jobs/{job.pk}/runs", {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())
    )
    assert response.status_code == 202
    row = BatchExecution.objects.get(pk=response.json()["id"])
    assert row.dispatch_error_code == "broker_publish_failed"
    monkeypatch.setattr(tasks.execute, "apply_async", worker.publish)
    delivery.reconcile(now=row.next_dispatch_at)
    worker.event(str(row.celery_task_id), "succeeded")
    row.refresh_from_db()
    assert row.status == "success" and NewsCandidate.objects.count() == 1


def test_retry_message_loss_recovered_from_ledger(worker, news_source, monkeypatch):
    from apps.batch import delivery, tasks

    worker.source = news_source
    worker.start("retry_publish_lost")
    task_id = worker.send()
    wait_for(
        lambda: BatchExecution.objects.filter(
            pk=worker.execution.pk, dispatch_error_code="retry_publish_failed"
        ).exists(),
        worker.output,
    )
    row = BatchExecution.objects.get(pk=worker.execution.pk)
    assert row.status == "retry_wait"
    monkeypatch.setattr(tasks.execute, "apply_async", worker.publish)
    delivery.reconcile(now=row.next_dispatch_at)
    worker.event(task_id, "succeeded")
    row.refresh_from_db()
    assert row.status == "success" and row.attempt == 2


def test_business_success_without_final_record_remains_uncertain(worker, news_source):
    worker.source = news_source
    worker.start("completion_lost")
    task_id = worker.send()
    wait_for(lambda: "execution_state_unconfirmed" in worker.output(), worker.output)
    assert NewsCandidate.objects.count() == 1
    row = BatchExecution.objects.get(pk=worker.execution.pk)
    assert row.status == "running"
    worker.send(execution=worker.execution)
    worker.event(task_id, "duplicate_ignored")
    assert NewsCandidate.objects.count() == 1


def test_confirmed_publish_record_loss_delivers_twice_but_starts_once(
    worker, news_source, monkeypatch
):
    from apps.batch import delivery, tasks

    worker.source = news_source
    job = BatchJob.objects.create(
        code="news_collection", name="News", source=news_source, enabled=True
    )
    with patch.object(services, "_kick"):
        row, _ = services.request_run(job_id=job.pk, key=uuid4())
    monkeypatch.setattr(tasks.execute, "apply_async", worker.publish)
    original = BatchExecution.save

    def lose_confirmation(self, *args, **kwargs):
        if self.last_published_at:
            raise RuntimeError("injected post-confirm failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BatchExecution, "save", lose_confirmation)
    with pytest.raises(RuntimeError):
        delivery.dispatch(row.pk)
    row.refresh_from_db()
    monkeypatch.setattr(BatchExecution, "save", original)
    delivery.reconcile(now=row.next_dispatch_at)
    worker.start()
    worker.event(str(row.celery_task_id), "succeeded")
    worker.event(str(row.celery_task_id), "duplicate_ignored")
    assert NewsCandidate.objects.count() == 1
    row.refresh_from_db()
    assert row.attempt == 1 and row.status == "success"


def test_actual_worker_token_cleanup_without_http(worker, news_source, user):
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    worker.source = news_source
    token = RefreshToken.for_user(user)
    OutstandingToken.objects.filter(jti=token["jti"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    job = BatchJob.objects.create(code="expired_token_cleanup", name="Cleanup", enabled=True)
    with patch.object(services, "_kick"):
        row, _ = services.request_run(job_id=job.pk, key=uuid4())
    worker.start()
    worker.event(worker.send(execution=row), "succeeded")
    row.refresh_from_db()
    assert row.status == "success"
    assert row.result_summary["attempts"][0]["counts"]["outstanding_deleted"] == 1
    assert not (worker.control / "requests").exists()
