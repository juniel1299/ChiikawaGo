from drf_spectacular.utils import extend_schema
from rest_framework import generics

from .models import Spot
from .selectors import nearby_spots
from .serializers import NearbyQuerySerializer, SpotSerializer


@extend_schema(parameters=[NearbyQuerySerializer])
class NearbyView(generics.ListAPIView):
    serializer_class = SpotSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Spot.objects.none()
        query = NearbyQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return nearby_spots(**query.validated_data)
