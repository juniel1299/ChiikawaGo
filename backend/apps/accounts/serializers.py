from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer

from .models import User
from .tokens import locked_refresh_token


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name", "date_joined")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    class Meta:
        model = User
        fields = ("id", "email", "display_name", "password", "date_joined")
        read_only_fields = ("id", "date_joined")

    def validate_email(self, value):
        value = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], display_name=attrs["display_name"])
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            # The DB constraint also handles two simultaneous registrations.
            if User.objects.filter(email__iexact=validated_data["email"]).exists():
                raise serializers.ValidationError(
                    {"email": "이미 사용 중인 이메일입니다."}
                ) from exc
            raise


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs["email"] = User.objects.normalize_email(attrs["email"])
        return super().validate(attrs)


class RefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        with locked_refresh_token(attrs["refresh"]) as token:
            if not User.objects.filter(pk=token["user_id"], is_active=True).exists():
                raise AuthenticationFailed("비활성 계정입니다.")
            return super().validate(attrs)


class TokenPairResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)
