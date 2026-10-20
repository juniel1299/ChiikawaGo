from collections.abc import Mapping

from rest_framework import serializers

from .models import Comment, Post, Report


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["허용되지 않은 요청 필드입니다."]}
            )
        return super().to_internal_value(data)


class PostInputSerializer(StrictInputSerializer):
    category = serializers.ChoiceField(choices=Post.Category.choices)
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(max_length=10000)


class CommentInputSerializer(StrictInputSerializer):
    content = serializers.CharField(max_length=2000)


class ReportInputSerializer(StrictInputSerializer):
    target_type = serializers.ChoiceField(choices=["post", "comment"])
    target_id = serializers.UUIDField()
    reason = serializers.ChoiceField(choices=Report.Reason.choices)
    details = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class AuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    display_name = serializers.CharField(read_only=True)


class PostListSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Post
        fields = (
            "id",
            "author",
            "category",
            "title",
            "created_at",
            "updated_at",
            "like_count",
            "comment_count",
            "is_liked",
        )
        read_only_fields = fields


class PostDetailSerializer(PostListSerializer):
    class Meta(PostListSerializer.Meta):
        fields = (*PostListSerializer.Meta.fields, "content")
        read_only_fields = fields


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    post_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "post_id", "author", "content", "created_at", "updated_at")
        read_only_fields = fields


class ReportSerializer(serializers.ModelSerializer):
    target_type = serializers.ChoiceField(choices=["post", "comment"], read_only=True)
    target_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Report
        fields = ("id", "target_type", "target_id", "status", "created_at")
        read_only_fields = fields
