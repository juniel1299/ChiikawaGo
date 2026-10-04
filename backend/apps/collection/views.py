from rest_framework import generics

from .models import CollectionEntry
from .serializers import CollectionEntrySerializer


class CollectionListView(generics.ListAPIView):
    serializer_class = CollectionEntrySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CollectionEntry.objects.none()
        return (
            CollectionEntry.objects.filter(user=self.request.user)
            .select_related("character_variant__character", "capture_result__encounter__spot")
            .order_by("-capture_result__captured_at", "-id")
        )
