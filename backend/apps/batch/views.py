from uuid import UUID

from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.news.models import Source

from . import services
from .models import BatchExecution, BatchJob, BatchSchedule
from .serializers import (
    CapabilitiesSerializer,
    ConfirmationInput,
    EmptyInput,
    ExecutionSerializer,
    JobInput,
    JobSerializer,
    ScheduleInput,
    ScheduleSerializer,
    ScheduleUpdateInput,
    SourceSerializer,
)


class BatchPermission(BasePermission):
    def has_permission(self, request, view):
        services.authorize(request.user)
        return True


class BatchView(APIView):
    permission_classes = [IsAuthenticated, BatchPermission]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


def validated(cls, request, partial=False):
    serializer = cls(data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def key(request):
    try:
        return UUID(request.headers.get("Idempotency-Key", ""))
    except (ValueError, AttributeError) as exc:
        raise ValidationError({"idempotency_key": "UUID Idempotency-Key가 필요합니다."}) from exc


class CapabilitiesView(BatchView):
    @extend_schema(responses=CapabilitiesSerializer)
    def get(self, request):
        return Response(
            {
                "view": True,
                "run": request.user.has_perm("batch.run_batch"),
                "manage": request.user.has_perm("batch.manage_batch"),
            }
        )


def jobs_with_execution_summary():
    executions = BatchExecution.objects.filter(job_id=OuterRef("pk"))
    return BatchJob.objects.order_by("code").annotate(
        last_execution_id=Subquery(executions.values("id")[:1]),
        last_execution_status=Subquery(executions.values("status")[:1]),
        current_execution_id=Subquery(
            executions.filter(status__in=["queued", "running", "retry_wait"]).values("id")[:1]
        ),
    )


class JobsView(BatchView):
    @extend_schema(responses=JobSerializer(many=True))
    def get(self, request):
        return Response(JobSerializer(jobs_with_execution_summary(), many=True).data)


class JobView(BatchView):
    @extend_schema(request=JobInput, responses=JobSerializer)
    def patch(self, request, pk):
        services.update_job(pk, validated(JobInput, request), request.user)
        return Response(JobSerializer(jobs_with_execution_summary().get(pk=pk)).data)


class SourcesView(BatchView):
    @extend_schema(responses=SourceSerializer(many=True))
    def get(self, request):
        return Response(SourceSerializer(Source.objects.order_by("code"), many=True).data)


class SchedulesView(BatchView):
    @extend_schema(responses=ScheduleSerializer(many=True))
    def get(self, request):
        return Response(ScheduleSerializer(BatchSchedule.objects.order_by("id"), many=True).data)

    @extend_schema(request=ScheduleInput, responses={201: ScheduleSerializer})
    def post(self, request):
        row = services.save_schedule(data=validated(ScheduleInput, request), user=request.user)
        return Response(ScheduleSerializer(row).data, status=201)


class ScheduleView(BatchView):
    @extend_schema(responses=ScheduleSerializer)
    def get(self, request, pk):
        return Response(ScheduleSerializer(get_object_or_404(BatchSchedule, pk=pk)).data)

    @extend_schema(request=ScheduleUpdateInput, responses=ScheduleSerializer)
    def patch(self, request, pk):
        row = services.save_schedule(
            data=validated(ScheduleUpdateInput, request, True), user=request.user, schedule_id=pk
        )
        return Response(ScheduleSerializer(row).data)


class RunView(BatchView):
    @extend_schema(
        request=EmptyInput,
        responses={200: ExecutionSerializer, 202: ExecutionSerializer},
        parameters=[OpenApiParameter("Idempotency-Key", str, location="header", required=True)],
    )
    def post(self, request, pk):
        validated(EmptyInput, request)
        row, created = services.request_run(
            job_id=pk,
            key=key(request),
            user=request.user,
            request_id=getattr(request, "request_id", None),
        )
        return Response(ExecutionSerializer(row).data, status=202 if created else 200)


class ExecutionsView(generics.ListAPIView, BatchView):
    serializer_class = ExecutionSerializer
    queryset = BatchExecution.objects.all()

    @extend_schema(
        parameters=[
            OpenApiParameter("job", str),
            OpenApiParameter("status", str, enum=BatchExecution.Status.values),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        query = super().get_queryset()
        if "job" in self.request.query_params:
            try:
                query = query.filter(job_id=UUID(self.request.query_params["job"]))
            except ValueError as exc:
                raise ValidationError({"job": "UUID가 필요합니다."}) from exc
        if "status" in self.request.query_params:
            value = self.request.query_params["status"]
            if value not in BatchExecution.Status.values:
                raise ValidationError({"status": "올바르지 않은 상태입니다."})
            query = query.filter(status=value)
        return query


class ExecutionView(BatchView):
    @extend_schema(responses=ExecutionSerializer)
    def get(self, request, pk):
        return Response(ExecutionSerializer(get_object_or_404(BatchExecution, pk=pk)).data)


class RetryView(BatchView):
    @extend_schema(
        request=EmptyInput,
        responses={200: ExecutionSerializer, 202: ExecutionSerializer},
        parameters=[OpenApiParameter("Idempotency-Key", str, location="header", required=True)],
    )
    def post(self, request, pk):
        validated(EmptyInput, request)
        original = get_object_or_404(BatchExecution, pk=pk)
        row, created = services.request_run(
            job_id=original.job_id,
            key=key(request),
            user=request.user,
            retry_of=pk,
            request_id=getattr(request, "request_id", None),
        )
        return Response(ExecutionSerializer(row).data, status=202 if created else 200)


class ConfirmFailureView(BatchView):
    @extend_schema(request=ConfirmationInput, responses=ExecutionSerializer)
    def post(self, request, pk):
        row = services.confirm_failure(pk, request.user, **validated(ConfirmationInput, request))
        return Response(ExecutionSerializer(row).data)
