from collections.abc import Mapping

from rest_framework import serializers

from apps.spatial.serializers import FiniteFloatField

from .models import CaptureResult, Encounter


class EncounterCreateSerializer(serializers.Serializer):
    spot_id = serializers.UUIDField()
    latitude = FiniteFloatField(min_value=-90, max_value=90)
    longitude = FiniteFloatField(min_value=-180, max_value=180)

    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            # Do not echo arbitrary field names/values into responses or logs.
            raise serializers.ValidationError(
                {"non_field_errors": ["허용되지 않은 요청 필드입니다."]}
            )
        return super().to_internal_value(data)


class EncounterSerializer(serializers.ModelSerializer):
    spot_id = serializers.UUIDField(read_only=True)
    character_variant_id = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(
        choices=Encounter.Status.choices, source="effective_status", read_only=True
    )

    class Meta:
        model = Encounter
        fields = ("id", "spot_id", "character_variant_id", "spawned_at", "expires_at", "status")
        read_only_fields = fields


class CaptureRequestSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and data:
            raise serializers.ValidationError(
                {"non_field_errors": ["허용되지 않은 요청 필드입니다."]}
            )
        return super().to_internal_value(data)


class CaptureResultSerializer(serializers.ModelSerializer):
    encounter_id = serializers.UUIDField(read_only=True)
    collection_entry_id = serializers.UUIDField(source="collection_entry.id", read_only=True)
    character_variant_id = serializers.UUIDField(
        source="encounter.character_variant_id", read_only=True
    )
    captured_spot_id = serializers.UUIDField(source="encounter.spot_id", read_only=True)
    status = serializers.ChoiceField(
        choices=["captured"], source="encounter.status", read_only=True
    )

    class Meta:
        model = CaptureResult
        fields = (
            "id",
            "encounter_id",
            "collection_entry_id",
            "character_variant_id",
            "captured_spot_id",
            "captured_at",
            "status",
        )
        read_only_fields = fields
