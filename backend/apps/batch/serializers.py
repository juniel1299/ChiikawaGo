from collections.abc import Mapping

from rest_framework import serializers

from .models import BatchExecution, BatchJob, BatchSchedule
from .registry import POLICIES


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["허용되지 않은 필드입니다."]})
        return super().to_internal_value(data)


class EmptyInput(StrictInput):
    pass


class JobInput(StrictInput):
    enabled = serializers.BooleanField(required=False)
    source_id = serializers.UUIDField(required=False, allow_null=True)


class ScheduleInput(StrictInput):
    job_id = serializers.UUIDField()
    cron_expression = serializers.CharField(max_length=128)
    timezone = serializers.ChoiceField(choices=["UTC", "Asia/Seoul"], default="Asia/Seoul")
    enabled = serializers.BooleanField(default=False)
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)


class ScheduleUpdateInput(ScheduleInput):
    job_id = None


class ConfirmationInput(StrictInput):
    worker_stopped = serializers.BooleanField()


class CapabilitiesSerializer(serializers.Serializer):
    view = serializers.BooleanField()
    run = serializers.BooleanField()
    manage = serializers.BooleanField()


class SourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class JobSerializer(serializers.ModelSerializer):
    last_execution_id = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    last_execution_status = serializers.CharField(read_only=True, allow_null=True, default=None)
    current_execution_id = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    source_id = serializers.UUIDField(allow_null=True, read_only=True)
    execution_policy = serializers.SerializerMethodField()

    class Meta:
        model = BatchJob
        fields = [
            "id",
            "code",
            "name",
            "description",
            "enabled",
            "source_id",
            "execution_policy",
            "last_execution_id",
            "last_execution_status",
            "current_execution_id",
        ]

    def get_execution_policy(self, obj) -> dict:
        return POLICIES[obj.code]


class ScheduleSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = BatchSchedule
        fields = [
            "id",
            "job_id",
            "cron_expression",
            "timezone",
            "enabled",
            "starts_at",
            "ends_at",
            "last_scheduled_at",
            "next_run_at",
        ]
        read_only_fields = fields


class ExecutionSerializer(serializers.ModelSerializer):
    input_snapshot = serializers.DictField(read_only=True)
    result_summary = serializers.DictField(read_only=True)
    job_id = serializers.UUIDField(read_only=True)
    schedule_id = serializers.UUIDField(read_only=True, allow_null=True)
    retry_of_id = serializers.UUIDField(read_only=True, allow_null=True)
    requested_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    recovery_confirmed_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    is_stale = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = BatchExecution
        fields = [
            "id",
            "job_id",
            "schedule_id",
            "scheduled_for",
            "retry_of_id",
            "trigger_type",
            "requested_by_id",
            "requested_at",
            "request_id",
            "input_snapshot",
            "status",
            "started_at",
            "attempt_started_at",
            "finished_at",
            "attempt",
            "next_attempt_at",
            "celery_task_id",
            "next_dispatch_at",
            "last_published_at",
            "publish_attempts",
            "dispatch_error_code",
            "worker",
            "result_summary",
            "failure_code",
            "safe_failure_message",
            "recovery_confirmed_by_id",
            "recovery_confirmed_at",
            "is_stale",
            "duration_seconds",
        ]
        read_only_fields = fields

    def get_is_stale(self, obj) -> bool:
        return obj.is_stale()

    def get_duration_seconds(self, obj) -> float | None:
        if not obj.started_at:
            return None
        from django.utils import timezone

        return max(0, ((obj.finished_at or timezone.now()) - obj.started_at).total_seconds())
