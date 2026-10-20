from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from .models import Character, CharacterVariant
from .serializers import CharacterSerializer, VariantSerializer


class CharacterListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CharacterSerializer
    queryset = Character.objects.filter(is_active=True)


class CharacterDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CharacterSerializer
    queryset = Character.objects.filter(is_active=True)


class VariantListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VariantSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CharacterVariant.objects.none()
        character = get_object_or_404(Character, pk=self.kwargs["pk"], is_active=True)
        return character.variants.filter(is_active=True)
