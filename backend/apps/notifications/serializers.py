from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["허용되지 않은 입력입니다."]})
        return super().to_internal_value(data)


class ProofSerializer(StrictSerializer):
    installation_secret = serializers.RegexField(r"^[A-Za-z0-9_-]{43,128}$", write_only=True)


class BindingSerializer(ProofSerializer):
    binding_version = serializers.IntegerField(min_value=1)


class RegistrationSerializer(BindingSerializer):
    binding_version = serializers.IntegerField(min_value=0)
    platform = serializers.ChoiceField(choices=["ios", "android"])
    provider_token = serializers.CharField(
        max_length=4096, allow_blank=True, write_only=True, trim_whitespace=False
    )
    enabled = serializers.BooleanField()
    permission_state = serializers.ChoiceField(
        choices=["not_determined", "denied", "authorized", "provisional"]
    )

    def validate(self, attrs):
        if attrs["enabled"] and (
            not attrs["provider_token"].strip()
            or attrs["permission_state"] not in ["authorized", "provisional"]
        ):
            raise serializers.ValidationError("권한과 전달 등록이 필요합니다.")
        return attrs


class DeviceResponse(serializers.Serializer):
    installation_id = serializers.UUIDField()
    binding_version = serializers.IntegerField()
    enabled = serializers.BooleanField()
