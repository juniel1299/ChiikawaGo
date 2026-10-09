from rest_framework import serializers

from .models import Category, News, Source


class NewsFilterSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.choices, required=False)


class NewsSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["code", "name"]
        read_only_fields = fields


class NewsSerializer(serializers.ModelSerializer):
    source = NewsSourceSerializer(read_only=True)

    class Meta:
        model = News
        fields = [
            "id",
            "title",
            "category",
            "summary",
            "source",
            "source_url",
            "published_at",
            "created_at",
        ]
        read_only_fields = fields
