import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

ACTIVE = ["queued", "running", "retry_wait"]


class BatchJob(models.Model):
    class Code(models.TextChoices):
        NEWS = "news_collection", "News 수집"
        TOKENS = "expired_token_cleanup", "만료 토큰 정리"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, choices=Code.choices)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    source = models.ForeignKey("news.Source", null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        permissions = [
            ("view_batch", "View batch platform"),
            ("run_batch", "Run batch jobs"),
            ("manage_batch", "Manage batch configuration"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(code__in=["news_collection", "expired_token_cleanup"]),
                name="batch_job_code",
            ),
            models.CheckConstraint(
                condition=Q(code="news_collection") | Q(source__isnull=True),
                name="batch_cleanup_no_source",
            ),
            models.CheckConstraint(
                condition=~Q(code="news_collection") | Q(enabled=False) | Q(source__isnull=False),
                name="batch_news_source",
            ),
        ]

    def __str__(self):
        return self.name


class BatchSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(BatchJob, on_delete=models.PROTECT, related_name="schedule")
    cron_expression = models.CharField(max_length=128)
    timezone = models.CharField(max_length=32, default="Asia/Seoul")
    enabled = models.BooleanField(default=False)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    last_scheduled_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.CheckConstraint(
                condition=Q(timezone__in=["Asia/Seoul", "UTC"]), name="batch_schedule_zone"
            ),
            models.CheckConstraint(
                condition=Q(starts_at__isnull=True)
                | Q(ends_at__isnull=True)
                | Q(starts_at__lt=models.F("ends_at")),
                name="batch_schedule_period",
            ),
        ]


class BatchExecution(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "대기"
        RUNNING = "running", "실행 중"
        RETRY_WAIT = "retry_wait", "자동 재시도 대기"
        SUCCESS = "success", "성공"
        FAILED = "failed", "실패"

    class Trigger(models.TextChoices):
        MANUAL = "manual", "수동"
        SCHEDULE = "schedule", "스케줄"
        RETRY = "retry", "운영자 재시도"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(BatchJob, on_delete=models.PROTECT, related_name="executions")
    schedule = models.ForeignKey(BatchSchedule, null=True, blank=True, on_delete=models.PROTECT)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    retry_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="retry_execution"
    )
    trigger_type = models.CharField(max_length=16, choices=Trigger.choices)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    requested_at = models.DateTimeField(default=timezone.now)
    request_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.UUIDField(null=True, blank=True)
    input_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    attempt_started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempt = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.UUIDField(null=True, blank=True, unique=True)
    next_dispatch_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_published_at = models.DateTimeField(null=True, blank=True)
    publish_attempts = models.PositiveIntegerField(default=0)
    dispatch_error_code = models.CharField(max_length=64, blank=True)
    worker = models.CharField(max_length=200, blank=True)
    result_summary = models.JSONField(default=dict)
    failure_code = models.CharField(max_length=64, blank=True)
    safe_failure_message = models.CharField(max_length=200, blank=True)
    recovery_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    recovery_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(fields=["job", "-requested_at", "-id"]),
            models.Index(fields=["status", "-requested_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["job"], condition=Q(status__in=ACTIVE), name="batch_one_active_job"
            ),
            models.UniqueConstraint(
                fields=["schedule", "scheduled_for"], name="batch_schedule_occurrence"
            ),
            models.UniqueConstraint(
                fields=["job", "requested_by", "idempotency_key"],
                name="batch_request_key",
                nulls_distinct=False,
                condition=Q(idempotency_key__isnull=False),
            ),
            models.CheckConstraint(
                condition=Q(status__in=["queued", "running", "retry_wait", "success", "failed"]),
                name="batch_execution_status",
            ),
            models.CheckConstraint(
                condition=Q(trigger_type__in=["manual", "schedule", "retry"]),
                name="batch_execution_trigger",
            ),
            models.CheckConstraint(condition=Q(attempt__lte=3), name="batch_attempt_limit"),
            models.CheckConstraint(
                condition=Q(status__in=ACTIVE, finished_at__isnull=True)
                | Q(status__in=["success", "failed"], finished_at__isnull=False),
                name="batch_finish_state",
            ),
            models.CheckConstraint(
                condition=~Q(status="running")
                | Q(started_at__isnull=False, attempt_started_at__isnull=False, attempt__gte=1),
                name="batch_running_times",
            ),
            models.CheckConstraint(
                condition=~Q(status="retry_wait")
                | Q(next_attempt_at__isnull=False, attempt__gte=1),
                name="batch_retry_time",
            ),
            models.CheckConstraint(
                condition=Q(
                    trigger_type="schedule", schedule__isnull=False, scheduled_for__isnull=False
                )
                | (
                    ~Q(trigger_type="schedule")
                    & Q(schedule__isnull=True, scheduled_for__isnull=True)
                ),
                name="batch_schedule_trigger",
            ),
            models.CheckConstraint(
                condition=Q(trigger_type="retry", retry_of__isnull=False)
                | (~Q(trigger_type="retry") & Q(retry_of__isnull=True)),
                name="batch_retry_origin",
            ),
        ]

    def is_stale(self, now=None):
        return bool(
            self.status == self.Status.RUNNING
            and self.attempt_started_at
            and (now or timezone.now())
            >= self.attempt_started_at + timedelta(seconds=self.input_snapshot["hard_limit"] + 120)
        )
