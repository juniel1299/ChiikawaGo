from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Encounter
from .serializers import (
    CaptureRequestSerializer,
    CaptureResultSerializer,
    EncounterCreateSerializer,
    EncounterSerializer,
)
from .services import capture_encounter, create_encounter


class EncounterCreateView(APIView):
    @extend_schema(
        request=EncounterCreateSerializer,
        responses={200: EncounterSerializer, 201: EncounterSerializer},
    )
    def post(self, request):
        serializer = EncounterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        encounter, created = create_encounter(user=request.user, **serializer.validated_data)
        return Response(EncounterSerializer(encounter).data, status=201 if created else 200)


class EncounterDetailView(generics.RetrieveAPIView):
    serializer_class = EncounterSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Encounter.objects.none()
        return Encounter.objects.filter(user=self.request.user)


class CaptureView(APIView):
    @extend_schema(
        operation_id="encounters_capture",
        request=CaptureRequestSerializer,
        responses={200: CaptureResultSerializer},
    )
    def post(self, request, pk):
        serializer = CaptureRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = capture_encounter(user=request.user, encounter_id=pk)
        return Response(CaptureResultSerializer(result).data)
