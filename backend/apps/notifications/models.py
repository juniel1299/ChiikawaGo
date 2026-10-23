import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class PushDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    installation_id = models.UUIDField(unique=True)
    secret_hash = models.CharField(max_length=64, editable=False)
    platform = models.CharField(max_length=7, choices=[("ios", "iOS"), ("android", "Android")])
    provider_token = models.TextField(blank=True, editable=False)
    token_hash = models.CharField(max_length=64, blank=True, editable=False)
    enabled = models.BooleanField(default=False)
    permission_state = models.CharField(
        max_length=16,
        choices=[(v, v) for v in ("not_determined", "denied", "authorized", "provisional")],
    )
    binding_version = models.PositiveBigIntegerField(default=1)
    last_registered_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(binding_version__gte=1), name="push_binding_positive"
            ),
            models.CheckConstraint(
                condition=Q(platform__in=["ios", "android"]), name="push_platform"
            ),
            models.CheckConstraint(
                condition=Q(
                    permission_state__in=["not_determined", "denied", "authorized", "provisional"]
                ),
                name="push_permission",
            ),
            models.CheckConstraint(
                condition=Q(enabled=False)
                | (
                    Q(permission_state__in=["authorized", "provisional"])
                    & ~Q(provider_token="")
                    & ~Q(token_hash="")
                ),
                name="push_enabled_token",
            ),
            models.UniqueConstraint(
                fields=["token_hash"], condition=Q(enabled=True), name="push_active_token_unique"
            ),
        ]

    def __str__(self):
        return str(self.id)


class PushMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=24, default="OPERATOR_TEST", editable=False)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="push_messages"
    )
    title = models.CharField(max_length=100, default="CHII WORLD 테스트 알림", editable=False)
    body = models.CharField(
        max_length=200, default="알림 연결을 확인합니다. 앱을 열어 주세요.", editable=False
    )
    destination = models.CharField(max_length=16, default="HOME", editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="push_requests"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.UUIDField()

    class Meta:
        permissions = [("send_operator_test", "Send operator test notification")]
        constraints = [
            models.CheckConstraint(
                condition=Q(type="OPERATOR_TEST", destination="HOME"), name="push_template_type"
            ),
            models.UniqueConstraint(
                fields=["requested_by", "idempotency_key"], name="push_request_unique"
            ),
        ]


class PushDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        SENDING = "SENDING"
        RETRY_WAIT = "RETRY_WAIT"
        SENT = "SENT"
        FAILED = "FAILED"
        UNKNOWN = "UNKNOWN"
        SKIPPED = "SKIPPED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(PushMessage, on_delete=models.PROTECT, related_name="deliveries")
    device = models.ForeignKey(PushDevice, on_delete=models.PROTECT)
    device_binding_version = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt = models.PositiveSmallIntegerField(default=0)
    celery_task_id = models.UUIDField(null=True)
    provider_message_id = models.CharField(max_length=256, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    safe_failure_message = models.CharField(max_length=200, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    provider_started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    next_attempt_at = models.DateTimeField(null=True)
    next_dispatch_at = models.DateTimeField(null=True)
    last_published_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "device"], name="push_message_device_unique"
            ),
            models.CheckConstraint(condition=Q(attempt__lte=3), name="push_attempt_limit"),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "PENDING",
                        "SENDING",
                        "RETRY_WAIT",
                        "SENT",
                        "FAILED",
                        "UNKNOWN",
                        "SKIPPED",
                    ]
                ),
                name="push_delivery_status",
            ),
        ]
        indexes = [models.Index(fields=["status", "next_dispatch_at"], name="push_dispatch_due")]
