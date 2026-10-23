from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.notifications import delivery
from apps.notifications.models import PushDelivery
from tests.broker.test_worker import wait_for  # noqa: F401
from tests.broker.test_worker import worker as _worker_fixture
from tests.integration.test_notifications import device, message

push_worker = _worker_fixture

pytestmark = [pytest.mark.broker, pytest.mark.django_db(transaction=True)]


def make_delivery(user, moderator):
    device(user)
    with patch("apps.notifications.services.enqueue_safely"):
        return message(moderator, user).deliveries.get()


def test_push_real_worker_duplicate(user, moderator, push_worker):
    worker = push_worker
    row = make_delivery(user, moderator)
    worker.start("push_success")
    worker.send_push(row)
    worker.send_push(row)
    wait_for(lambda: PushDelivery.objects.filter(pk=row.pk, status="SENT").exists(), worker.output)
    # Wait for both tasks, not just the first DB completion.
    wait_for(lambda: worker.output().count("succeeded in") >= 2, worker.output)
    assert (worker.control / "push_calls").read_text().splitlines() == ["call"]
    row.refresh_from_db()
    assert row.attempt == 1 and row.provider_message_id == "synthetic-accepted"


def test_push_real_worker_retry_limit(user, moderator, push_worker):
    worker = push_worker
    row = make_delivery(user, moderator)
    worker.start("push_transient")
    for attempt in range(1, 4):
        worker.send_push(row, attempt)
        expected = "FAILED" if attempt == 3 else "RETRY_WAIT"
        wait_for(
            lambda attempt=attempt, expected=expected: PushDelivery.objects.filter(
                pk=row.pk, attempt=attempt, status=expected
            ).exists(),
            worker.output,
        )
        PushDelivery.objects.filter(pk=row.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
    assert len((worker.control / "push_calls").read_text().splitlines()) == 3


def test_push_worker_loss_unknown_no_replay(user, moderator, push_worker):
    worker = push_worker
    row = make_delivery(user, moderator)
    worker.start("push_lost")
    worker.send_push(row)
    wait_for(lambda: "WorkerLostError" in worker.output(), worker.output)
    PushDelivery.objects.filter(pk=row.pk).update(
        started_at=timezone.now() - timedelta(seconds=241)
    )
    delivery.reconcile()
    row.refresh_from_db()
    assert row.status == "UNKNOWN"
    worker.send_push(row)
    wait_for(lambda: "succeeded in" in worker.output(), worker.output)
    assert (worker.control / "push_calls").read_text().splitlines() == ["call"]
