from rest_framework import serializers

from apps.characters.models import Character, CharacterVariant
from apps.spatial.models import Spot

from .models import CollectionEntry


class CollectedCharacterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Character
        fields = ("id", "code", "name")
        read_only_fields = fields


class CollectedVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacterVariant
        fields = ("id", "code", "name", "rarity", "asset_key")
        read_only_fields = fields


class CapturedSpotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Spot
        fields = ("id", "code", "name")
        read_only_fields = fields


class CollectionEntrySerializer(serializers.ModelSerializer):
    encounter_id = serializers.UUIDField(source="capture_result.encounter_id", read_only=True)
    character = CollectedCharacterSerializer(source="character_variant.character", read_only=True)
    character_variant = CollectedVariantSerializer(read_only=True)
    captured_at = serializers.DateTimeField(source="capture_result.captured_at", read_only=True)
    captured_spot = CapturedSpotSerializer(source="capture_result.encounter.spot", read_only=True)

    class Meta:
        model = CollectionEntry
        fields = (
            "id",
            "encounter_id",
            "character",
            "character_variant",
            "captured_at",
            "captured_spot",
        )
        read_only_fields = fields
