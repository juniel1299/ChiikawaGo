from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.batch import delivery, services, tasks
from apps.batch.models import BatchExecution, BatchJob, BatchSchedule
from apps.batch.registry import Outcome
from apps.batch.schedules import latest_due, next_run, validate_schedule

pytestmark = pytest.mark.django_db


@pytest.fixture
def job():
    return BatchJob.objects.create(code="expired_token_cleanup", name="Cleanup", enabled=True)


@pytest.fixture
def queued(job):
    return services.request_run(job_id=job.pk, key=uuid4())[0]


def test_bootstrap_is_explicit_disabled_and_idempotent():
    call_command("configure_batch_jobs")
    call_command("configure_batch_jobs")
    assert BatchJob.objects.count() == 2
    assert not BatchJob.objects.filter(enabled=True).exists()
    assert not BatchSchedule.objects.exists()


@pytest.mark.parametrize(
    "cron,zone",
    [
        ("0 0 31 2 *", "UTC"),
        ("@daily", "UTC"),
        ("0 0 * * MON", "UTC"),
        ("* * * * * *", "UTC"),
        ("* * * * *", "America/New_York"),
        ("61 * * * *", "UTC"),
    ],
)
def test_invalid_cron(cron, zone):
    with pytest.raises(APIException):
        validate_schedule(cron, zone)


def test_timezone_start_end_leap_and_or_semantics():
    now = datetime(2026, 10, 11, tzinfo=UTC)
    schedule = BatchSchedule(cron_expression="0 9 * * *", timezone="Asia/Seoul", enabled=True)
    assert next_run(schedule, now) == now + timedelta(days=1)
    schedule.starts_at = now + timedelta(days=2)
    assert next_run(schedule, now) == schedule.starts_at
    schedule.ends_at = schedule.starts_at
    assert next_run(schedule, now) is None
    schedule.starts_at = schedule.ends_at = None
    schedule.timezone = "UTC"
    schedule.cron_expression = "0 0 29 2 *"
    assert next_run(schedule, now) == datetime(2028, 2, 29, tzinfo=UTC)
    schedule.cron_expression = "0 0 1 * 1"
    assert next_run(schedule, now) == datetime(2026, 10, 12, tzinfo=UTC)
    assert latest_due(schedule, now) == datetime(2026, 10, 5, tzinfo=UTC)


def test_accept_idempotency_busy_and_constraint(job):
    key = uuid4()
    first, created = services.request_run(job_id=job.pk, key=key)
    assert created
    assert services.request_run(job_id=job.pk, key=key) == (first, False)
    with pytest.raises(APIException):
        services.request_run(job_id=job.pk, key=uuid4())
    with pytest.raises(IntegrityError), transaction.atomic():
        BatchExecution.objects.create(
            job=job, trigger_type="manual", input_snapshot=first.input_snapshot
        )


def test_claim_duplicate_retry_and_terminal(queued, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr(services.random, "uniform", lambda a, b: 0)
    queued.input_snapshot["max_retries"] = 2
    queued.save()
    assert services.claim(queued.pk, 2, "worker") is None
    assert services.claim(queued.pk, 1, "worker")
    assert services.claim(queued.pk, 1, "worker") is None
    outcome = Outcome({"failed": 1}, ({"code": "network_timeout", "stage": "fetch"},), True)
    for attempt in range(1, 4):
        row = services.finish_attempt(queued.pk, attempt, outcome, now=now)
        if attempt < 3:
            assert row.status == "retry_wait"
            assert services.claim(row.pk, attempt, "worker", now=now) is None
            assert services.claim(row.pk, attempt + 1, "worker", now=now)
    assert row.status == "failed" and row.failure_code == "retry_exhausted"
    assert len(row.result_summary["attempts"]) == 3
    assert services.claim(row.pk, 3, "worker") is None


def test_dispatch_commit_rollback_failure_and_reconcile(
    job, monkeypatch, django_capture_on_commit_callbacks
):
    publish = Mock(side_effect=OSError("private"))
    monkeypatch.setattr(tasks.execute, "apply_async", publish)
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            row, _ = services.request_run(job_id=job.pk, key=uuid4())
            publish.assert_not_called()
    row.refresh_from_db()
    assert row.status == "queued" and row.dispatch_error_code == "broker_publish_failed"
    publish.side_effect = None
    delivery.reconcile(now=row.next_dispatch_at)
    row.refresh_from_db()
    assert row.last_published_at and row.publish_attempts == 2
    assert publish.call_args.kwargs["args"] == [str(row.pk), 1]
    services.claim(row.pk, 1, "w")
    services.finish_attempt(row.pk, 1, Outcome({}))
    publish.reset_mock()
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            services.request_run(job_id=job.pk, key=uuid4())
            raise RuntimeError()
    publish.assert_not_called()
    assert BatchExecution.objects.count() == 1


def test_recovery_is_manual_and_late_completion_cannot_overwrite(queued, moderator):
    now = timezone.now()
    row = services.claim(queued.pk, 1, "worker", now=now - timedelta(seconds=781))
    assert row.is_stale(now)
    with pytest.raises(APIException):
        services.confirm_failure(row.pk, moderator, worker_stopped=False, now=now)
    recovered = services.confirm_failure(row.pk, moderator, worker_stopped=True, now=now)
    assert recovered.status == "failed"
    late = services.finish_attempt(row.pk, 1, Outcome({"created": 1}))
    assert late.failure_code == "worker_outcome_unconfirmed"
    retry, created = services.request_run(
        job_id=row.job_id, key=uuid4(), user=moderator, retry_of=row.pk
    )
    assert created and retry.retry_of_id == row.pk
    assert services.request_run(
        job_id=row.job_id, key=uuid4(), user=moderator, retry_of=row.pk
    ) == (retry, False)
    row.refresh_from_db()
    assert row.status == "failed"


def test_due_misfire_busy_and_schedule_edit(job, moderator, monkeypatch):
    monkeypatch.setattr(services, "_kick", lambda row: None)
    now = timezone.now().replace(second=0, microsecond=0)
    schedule = services.save_schedule(
        data={"job_id": job.pk, "cron_expression": "* * * * *", "timezone": "UTC", "enabled": True},
        user=moderator,
    )
    schedule.next_run_at = now - timedelta(hours=3)
    schedule.save()
    first = services.schedule_due(job.pk, now)
    assert first.scheduled_for == now
    schedule.refresh_from_db()
    assert schedule.next_run_at == now + timedelta(minutes=1)
    assert services.schedule_due(job.pk, now + timedelta(minutes=5)) is None
    services.claim(first.pk, 1, "w")
    services.finish_attempt(first.pk, 1, Outcome({}))
    second = services.schedule_due(job.pk, now + timedelta(minutes=5))
    assert second.scheduled_for == now + timedelta(minutes=5)
    services.save_schedule(data={"enabled": False}, user=moderator, schedule_id=schedule.pk)
    schedule.refresh_from_db()
    assert schedule.next_run_at is None


def test_api_permissions_and_contract(client, user, moderator, job):
    assert client.get("/api/v1/batch/jobs").status_code == 401
    client.force_authenticate(user)
    # moderator fixture modifies this same user; remove staff to test ordinary access.
    user.is_staff = False
    user.save()
    assert client.get("/api/v1/batch/jobs").status_code == 403
    user.is_staff = True
    user.save()
    assert client.get("/api/v1/batch/capabilities").json() == {
        "view": True,
        "run": True,
        "manage": True,
    }
    key = str(uuid4())
    url = f"/api/v1/batch/jobs/{job.pk}/runs"
    assert client.post(url, {}, format="json").status_code == 400
    response = client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 202 and response["Cache-Control"] == "no-store"
    assert client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    assert (
        client.post(url, {"handler": "evil"}, format="json", HTTP_IDEMPOTENCY_KEY=key).status_code
        == 400
    )
    assert client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 409
    listing = client.get("/api/v1/batch/executions").json()
    assert listing["count"] == 1 and listing["results"][0]["status"] == "queued"
    assert client.get("/api/v1/batch/executions?status=unknown").status_code == 400
    assert client.get("/api/v1/batch/executions?job=bad").status_code == 400


def test_sync_command_has_no_dispatch(job):
    row, _ = services.request_run(job_id=job.pk, key=uuid4(), sync=True)
    assert row.status == "running" and row.celery_task_id is None
    assert not delivery.dispatch(row.pk)
    outcome = services.run_attempt(row)
    assert not outcome.errors
    assert services.finish_attempt(row.pk, 1, outcome).status == "success"


def test_retry_key_reuse_conflicts(queued, moderator):
    services.claim(queued.pk, 1, "w")
    services.finish_attempt(queued.pk, 1, Outcome({}, ({"code": "failed", "stage": "execution"},)))
    key = uuid4()
    services.request_run(job_id=queued.job_id, key=key, user=moderator, retry_of=queued.pk)
    with pytest.raises(APIException):
        services.request_run(job_id=queued.job_id, key=key, user=moderator)


def test_delivery_confirmed_but_record_write_lost_is_recoverable(queued, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(tasks.execute, "apply_async", publish)
    original = BatchExecution.save

    def fail_after_publish(self, *args, **kwargs):
        if self.last_published_at:
            raise RuntimeError("injected post-confirm DB failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BatchExecution, "save", fail_after_publish)
    with pytest.raises(RuntimeError):
        delivery.dispatch(queued.pk)
    queued.refresh_from_db()
    assert queued.status == "queued" and queued.next_dispatch_at > timezone.now()
    monkeypatch.setattr(BatchExecution, "save", original)
    delivery.reconcile(now=queued.next_dispatch_at)
    assert publish.call_count == 2
    assert services.claim(queued.pk, 1, "one") and services.claim(queued.pk, 1, "two") is None


def test_staff_requires_explicit_permissions(client, user, job):
    from django.contrib.auth.models import Permission

    user.is_staff = True
    user.save()
    client.force_authenticate(user)
    assert client.get("/api/v1/batch/jobs").status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_batch"))
    # Refresh cached Django permission results as a new request authentication would.
    from apps.accounts.models import User

    user = User.objects.get(pk=user.pk)
    client.force_authenticate(user)
    assert client.get("/api/v1/batch/jobs").status_code == 200
    assert (
        client.patch(f"/api/v1/batch/jobs/{job.pk}", {"enabled": False}, format="json").status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/batch/jobs/{job.pk}/runs",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        ).status_code
        == 403
    )


def test_source_change_busy_and_job_disable_preserves_acceptance(news_job, news_source, moderator):
    row, _ = services.request_run(job_id=news_job.pk, key=uuid4())
    with pytest.raises(APIException):
        services.update_job(news_job.pk, {"source_id": None}, moderator)
    services.update_job(news_job.pk, {"enabled": False}, moderator)
    assert services.claim(row.pk, 1, "worker")
    row.refresh_from_db()
    assert row.input_snapshot["source_id"] == str(news_source.pk)


def test_readonly_admin_cannot_mutate_even_superuser(moderator):
    from django.contrib import admin
    from django.test import RequestFactory

    request = RequestFactory().get("/admin/")
    request.user = moderator
    for model in (BatchJob, BatchSchedule, BatchExecution):
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


@pytest.mark.parametrize(
    "values",
    [
        {"code": "arbitrary.module"},
        {"code": "news_collection", "enabled": True},
    ],
)
def test_job_database_constraints(values):
    with pytest.raises(IntegrityError), transaction.atomic():
        BatchJob.objects.create(name="Invalid", **values)


def test_null_operator_request_key_stays_unique_after_completion(queued):
    services.claim(queued.pk, 1, "worker")
    services.finish_attempt(queued.pk, 1, Outcome({}))
    with pytest.raises(IntegrityError), transaction.atomic():
        BatchExecution.objects.create(
            job=queued.job, trigger_type="manual", idempotency_key=queued.idempotency_key
        )


def test_schedule_mutation_rejects_unknown_fields_and_invalid_period(client, moderator, job):
    client.force_authenticate(moderator)
    url = "/api/v1/batch/schedules"
    response = client.post(
        url,
        {"job_id": str(job.pk), "cron_expression": "0 9 * * *", "timezone": "Asia/Seoul"},
        format="json",
    )
    assert response.status_code == 201
    detail = f"{url}/{response.json()['id']}"
    assert client.patch(detail, {"job_id": str(uuid4())}, format="json").status_code == 400
    assert client.patch(detail, {"cron_expression": "@daily"}, format="json").status_code == 400
    assert (
        client.patch(
            detail,
            {"starts_at": "2026-10-12T00:00:00Z", "ends_at": "2026-10-11T00:00:00Z"},
            format="json",
        ).status_code
        == 400
    )
    assert client.get(detail).json()["cron_expression"] == "0 9 * * *"


def test_execution_pagination_and_stable_order(client, moderator, job):
    now = timezone.now()
    rows = []
    for _ in range(22):
        rows.append(
            BatchExecution.objects.create(
                job=job, trigger_type="manual", status="success", finished_at=now, requested_at=now
            )
        )
    client.force_authenticate(moderator)
    first = client.get("/api/v1/batch/executions").json()
    second = client.get("/api/v1/batch/executions?page=2").json()
    assert len(first["results"]) == 20 and len(second["results"]) == 2
    assert first["next"] and second["previous"]
    assert [r["id"] for r in first["results"] + second["results"]] == [
        str(r.pk) for r in sorted(rows, key=lambda r: r.pk, reverse=True)
    ]
    assert len(client.get("/api/v1/batch/executions?page_size=999").json()["results"]) == 22


def test_fast_worker_completion_still_records_publish_confirmation(queued, monkeypatch):
    def complete(**kwargs):
        services.claim(queued.pk, 1, "fast-worker")
        services.finish_attempt(queued.pk, 1, Outcome({}))

    monkeypatch.setattr(tasks.execute, "apply_async", complete)
    assert delivery.dispatch(queued.pk)
    queued.refresh_from_db()
    assert queued.status == "success" and queued.last_published_at
    assert queued.next_dispatch_at is None


def test_job_summary_is_preserved_on_patch(client, moderator, queued):
    client.force_authenticate(moderator)
    response = client.patch(
        f"/api/v1/batch/jobs/{queued.job_id}", {"enabled": False}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["current_execution_id"] == str(queued.pk)
    assert response.json()["last_execution_status"] == "queued"
