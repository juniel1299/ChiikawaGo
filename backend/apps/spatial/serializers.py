import math

from rest_framework import serializers

from .models import Spot


class FiniteFloatField(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail("invalid")
        return value


class NearbyQuerySerializer(serializers.Serializer):
    latitude = FiniteFloatField(min_value=-90, max_value=90)
    longitude = FiniteFloatField(min_value=-180, max_value=180)
    radius_m = FiniteFloatField(min_value=0, max_value=5000, default=1000)

    def validate_radius_m(self, value):
        if value <= 0:
            raise serializers.ValidationError("반경은 0보다 커야 합니다.")
        return value


class CoordinateSerializer(serializers.Serializer):
    latitude = serializers.FloatField(source="y")
    longitude = serializers.FloatField(source="x")


class SpotSerializer(serializers.ModelSerializer):
    location = CoordinateSerializer(read_only=True)
    distance_m = serializers.FloatField(source="distance.m", read_only=True)

    class Meta:
        model = Spot
        fields = (
            "id",
            "code",
            "name",
            "description",
            "location",
            "interaction_radius_m",
            "distance_m",
        )
