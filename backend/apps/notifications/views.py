from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import BindingSerializer, DeviceResponse, ProofSerializer, RegistrationSerializer


class DeviceView(APIView):
    @extend_schema(
        request=RegistrationSerializer, responses={200: DeviceResponse, 201: DeviceResponse}
    )
    def put(self, request, installation_id):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, created = services.register(
            user=request.user, installation_id=installation_id, **serializer.validated_data
        )
        return Response(DeviceResponse(device).data, status=201 if created else 200)

    @extend_schema(request=BindingSerializer, responses={204: None})
    def delete(self, request, installation_id):
        serializer = BindingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.unregister(
            user=request.user, installation_id=installation_id, **serializer.validated_data
        )
        return Response(status=204)


class ResolveView(APIView):
    @extend_schema(request=ProofSerializer, responses={200: DeviceResponse})
    def post(self, request, installation_id):
        serializer = ProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = services.resolve(
            installation_id=installation_id, secret=serializer.validated_data["installation_secret"]
        )
        return Response(DeviceResponse(device).data)
