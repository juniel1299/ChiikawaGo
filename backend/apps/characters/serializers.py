from rest_framework import serializers

from .models import Character, CharacterVariant


class CharacterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Character
        fields = ("id", "code", "name", "description")


class VariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacterVariant
        fields = ("id", "character", "code", "name", "rarity", "asset_key")
