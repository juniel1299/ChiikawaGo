from django.db.models import BooleanField, Count, Exists, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from .models import Comment, ContentStatus, Like, Post


def posts_for(user):
    likes = Like.objects.filter(post_id=OuterRef("pk"))
    comments = Comment.objects.filter(post_id=OuterRef("pk"), status=ContentStatus.VISIBLE)
    return (
        Post.objects.filter(status=ContentStatus.VISIBLE)
        .select_related("author")
        .annotate(
            like_count=Coalesce(
                Subquery(likes.values("post_id").annotate(n=Count("pk")).values("n")),
                0,
                output_field=IntegerField(),
            ),
            comment_count=Coalesce(
                Subquery(comments.values("post_id").annotate(n=Count("pk")).values("n")),
                0,
                output_field=IntegerField(),
            ),
            is_liked=Exists(likes.filter(user=user))
            if user.is_authenticated
            else Value(False, output_field=BooleanField()),
        )
        .order_by("-created_at", "-id")
    )
