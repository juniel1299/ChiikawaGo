import logging
import random
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from apps.news.models import Source
from apps.news.parser import CollectionError
from apps.news.services import require_source
from config.error_logging import log_internal_exception

from .models import ACTIVE, BatchExecution, BatchJob, BatchSchedule
from .registry import HANDLERS, POLICIES
from .schedules import latest_due, next_run, validate_schedule

logger = logging.getLogger("chii.tasks")


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"


def conflict(reason):
    raise Conflict({"reason": reason})


def authorize(user, *permissions):
    if (
        not user
        or not user.is_active
        or not user.is_staff
        or not user.has_perms(["batch.view_batch", *["batch." + p for p in permissions]])
    ):
        raise PermissionDenied("Batch 권한이 필요합니다.")


def job_locked(job_id):
    try:
        return BatchJob.objects.select_for_update(no_key=True).get(pk=job_id)
    except BatchJob.DoesNotExist as exc:
        raise NotFound() from exc


def validate_source(source_id):
    try:
        source = Source.objects.get(pk=source_id)
        require_source(source)
    except (Source.DoesNotExist, CollectionError) as exc:
        raise ValidationError({"source_id": "활성 상태와 정책 확인을 검토하세요."}) from exc


def snapshot_for(job):
    if not job.enabled:
        conflict("job_disabled")
    if job.code == BatchJob.Code.NEWS:
        validate_source(job.source_id)
    return {
        "code": job.code,
        "source_id": str(job.source_id) if job.source_id else None,
        **POLICIES[job.code],
    }


def active_exists(job):
    return BatchExecution.objects.filter(job=job, status__in=ACTIVE).exists()


def _create(job, *, snapshot, now, sync=False, **fields):
    if active_exists(job):
        conflict("job_busy")
    if sync:
        snapshot = {**snapshot, "max_retries": 0}
    return BatchExecution.objects.create(
        job=job,
        input_snapshot=snapshot,
        requested_at=now,
        celery_task_id=None if sync else uuid4(),
        next_dispatch_at=None if sync else now,
        status="running" if sync else "queued",
        attempt=1 if sync else 0,
        started_at=now if sync else None,
        attempt_started_at=now if sync else None,
        worker="management_command" if sync else "",
        **fields,
    )


def _kick(execution):
    from .delivery import dispatch

    def after_commit():
        try:
            dispatch(execution.pk)
        except Exception as exc:
            # Acceptance is already durable; reconciliation recovers interrupted dispatch.
            log_internal_exception(exc, SimpleNamespace(request_id=str(execution.pk)))

    transaction.on_commit(after_commit)


def request_run(*, job_id, key, user=None, request_id=None, retry_of=None, sync=False, now=None):
    now = now or timezone.now()
    key = UUID(str(key))
    with transaction.atomic():
        if user is not None:
            authorize(user, "run_batch")
        job = job_locked(job_id)
        previous = BatchExecution.objects.filter(
            job=job, requested_by=user, idempotency_key=key
        ).first()
        if previous:
            if previous.retry_of_id != retry_of:
                conflict("idempotency_key_reused")
            return previous, False
        original = None
        if retry_of:
            original = (
                BatchExecution.objects.select_for_update().filter(pk=retry_of, job=job).first()
            )
            if not original:
                raise NotFound()
            if original.status != "failed":
                conflict("execution_not_failed")
            existing = BatchExecution.objects.filter(retry_of=original).first()
            if existing:
                return existing, False
        snapshot = snapshot_for(job)
        if original:
            snapshot = original.input_snapshot.copy()
            if snapshot["code"] == BatchJob.Code.NEWS:
                validate_source(snapshot["source_id"])
        execution = _create(
            job,
            snapshot=snapshot,
            now=now,
            sync=sync,
            trigger_type="retry" if original else "manual",
            requested_by=user,
            request_id=request_id,
            idempotency_key=key,
            retry_of=original,
        )
        if not sync:
            _kick(execution)
        return execution, True


def update_job(job_id, data, user):
    with transaction.atomic():
        authorize(user, "manage_batch")
        job = job_locked(job_id)
        if "source_id" in data and data["source_id"] != job.source_id and active_exists(job):
            conflict("job_busy")
        source_id = data.get("source_id", job.source_id)
        if job.code != BatchJob.Code.NEWS and source_id:
            raise ValidationError({"source_id": "토큰 정리는 Source를 사용하지 않습니다."})
        if source_id and not Source.objects.filter(pk=source_id).exists():
            raise ValidationError({"source_id": "존재하지 않는 Source입니다."})
        was_enabled = job.enabled
        job.source_id = source_id
        job.enabled = data.get("enabled", job.enabled)
        if job.enabled and job.code == BatchJob.Code.NEWS:
            validate_source(job.source_id)
        job.save()
        if job.enabled and not was_enabled:
            schedule = BatchSchedule.objects.select_for_update().filter(job=job).first()
            if schedule:
                schedule.next_run_at = next_run(schedule, timezone.now())
                schedule.save()
        return job


def save_schedule(*, data, user, schedule_id=None):
    if schedule_id:
        job_id = (
            BatchSchedule.objects.filter(pk=schedule_id).values_list("job_id", flat=True).first()
        )
        if not job_id:
            raise NotFound()
    else:
        job_id = data["job_id"]
    with transaction.atomic():
        authorize(user, "manage_batch")
        job = job_locked(job_id)
        schedule = BatchSchedule.objects.select_for_update().filter(job=job).first()
        if not schedule_id and schedule:
            conflict("schedule_exists")
        if schedule is None:
            schedule = BatchSchedule(job=job)
        for field, value in data.items():
            if field != "job_id":
                setattr(schedule, field, value)
        validate_schedule(
            schedule.cron_expression, schedule.timezone, schedule.starts_at, schedule.ends_at
        )
        schedule.next_run_at = next_run(schedule, timezone.now())
        schedule.save()
        return schedule


def schedule_due(job_id, now):
    with transaction.atomic():
        job = (
            BatchJob.objects.select_for_update(skip_locked=True, no_key=True)
            .filter(pk=job_id)
            .first()
        )
        if not job or not job.enabled:
            return None
        schedule = (
            BatchSchedule.objects.select_for_update()
            .filter(job=job, enabled=True, next_run_at__lte=now)
            .first()
        )
        if not schedule:
            return None
        if schedule.ends_at and now >= schedule.ends_at:
            schedule.next_run_at = None
            schedule.save()
            return None
        if active_exists(job):
            return None
        # Invalid/disabled sources are recorded by the worker, without blocking every tick.
        snapshot = {
            "code": job.code,
            "source_id": str(job.source_id) if job.source_id else None,
            **POLICIES[job.code],
        }
        due = latest_due(schedule, now)
        execution = _create(
            job,
            snapshot=snapshot,
            now=now,
            trigger_type="schedule",
            schedule=schedule,
            scheduled_for=due,
        )
        schedule.last_scheduled_at = due
        schedule.next_run_at = next_run(schedule, now)
        schedule.save()
        _kick(execution)
        return execution


def lock_execution(execution_id):
    job_id = BatchExecution.objects.filter(pk=execution_id).values_list("job_id", flat=True).first()
    if not job_id:
        raise NotFound()
    job_locked(job_id)
    return BatchExecution.objects.select_for_update().get(pk=execution_id)


def claim(execution_id, attempt, worker, now=None):
    with transaction.atomic():
        execution = lock_execution(execution_id)
        now = now or timezone.now()
        if execution.status not in ["queued", "retry_wait"] or attempt != execution.attempt + 1:
            return None
        if not execution.celery_task_id or (
            execution.next_attempt_at and execution.next_attempt_at > now
        ):
            return None
        execution.status = "running"
        execution.attempt = attempt
        execution.started_at = execution.started_at or now
        execution.attempt_started_at = now
        execution.worker = worker[:200]
        execution.dispatch_error_code = ""
        execution.next_dispatch_at = None
        execution.next_attempt_at = None
        execution.save()
        return execution


def run_attempt(execution):
    from .registry import Outcome

    try:
        return HANDLERS[execution.input_snapshot["code"]](execution.input_snapshot)
    except SoftTimeLimitExceeded:
        return Outcome({}, ({"code": "time_limit", "stage": "execution"},))
    except Exception as exc:
        log_internal_exception(exc, SimpleNamespace(request_id=str(execution.pk)))
        return Outcome({}, ({"code": "internal_error", "stage": "execution"},))


def finish_attempt(execution_id, attempt, outcome, now=None):
    with transaction.atomic():
        execution = lock_execution(execution_id)
        if execution.status != "running" or execution.attempt != attempt:
            return execution
        now = now or timezone.now()
        summaries = execution.result_summary.get("attempts", [])
        summaries.append(
            {"attempt": attempt, "counts": outcome.counts, "errors": list(outcome.errors)}
        )
        execution.result_summary = {"attempts": summaries}
        if (
            outcome.errors
            and outcome.retryable
            and attempt <= execution.input_snapshot["max_retries"]
        ):
            delay = random.uniform(0, min(60 * 2 ** (attempt - 1), 120))
            execution.status = "retry_wait"
            execution.next_attempt_at = now + timedelta(seconds=delay)
            # Celery normally publishes immediately; reconciliation waits until due + grace.
            execution.next_dispatch_at = execution.next_attempt_at + timedelta(seconds=120)
        else:
            execution.status = "failed" if outcome.errors else "success"
            execution.finished_at = now
            execution.failure_code = (
                ("retry_exhausted" if outcome.retryable else outcome.errors[0]["code"])
                if outcome.errors
                else ""
            )
            execution.safe_failure_message = (
                "실행을 완료하지 못했습니다. 실행 ID로 서버 로그를 확인하세요."
                if outcome.errors
                else ""
            )
        execution.save()
        return execution


def confirm_failure(execution_id, user, *, worker_stopped, now=None):
    with transaction.atomic():
        authorize(user, "run_batch", "manage_batch")
        execution = lock_execution(execution_id)
        if execution.recovery_confirmed_at:
            return execution
        if not worker_stopped or not execution.is_stale(now):
            conflict("recovery_confirmation_required")
        execution.status = "failed"
        execution.finished_at = now or timezone.now()
        execution.failure_code = "worker_outcome_unconfirmed"
        execution.safe_failure_message = (
            "운영자가 기존 실행 종료를 확인했습니다. 업무 결과는 불확실할 수 있습니다."
        )
        execution.recovery_confirmed_by = user
        execution.recovery_confirmed_at = execution.finished_at
        execution.save()
        return execution
