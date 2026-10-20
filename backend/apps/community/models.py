import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ContentStatus(models.TextChoices):
    VISIBLE = "visible", "공개"
    HIDDEN = "hidden", "숨김"
    DELETED = "deleted", "삭제"


class Post(models.Model):
    class Category(models.TextChoices):
        FREE = "free", "자유"
        GOODS = "goods", "굿즈"
        COLLECTION = "collection", "캐릭터 자랑"
        SPOT = "spot", "Spot 제보"
        GUIDE = "guide", "공략"
        EVENT = "event", "이벤트"
        TRADE = "trade", "교환"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=200)
    content = models.TextField(max_length=10000)
    status = models.CharField(
        max_length=16, choices=ContentStatus.choices, default=ContentStatus.VISIBLE
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [("moderate_post", "Can hide and restore posts")]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    category__in=["free", "goods", "collection", "spot", "guide", "event", "trade"]
                ),
                name="community_post_category",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ContentStatus.values), name="community_post_status"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="deleted", deleted_at__isnull=False, title="", content="")
                    | (~Q(status="deleted") & Q(deleted_at__isnull=True))
                ),
                name="community_post_deletion",
            ),
        ]
        indexes = [
            models.Index(
                fields=["-created_at", "-id"],
                condition=Q(status="visible"),
                name="community_post_latest",
            ),
            models.Index(
                fields=["category", "-created_at", "-id"],
                condition=Q(status="visible"),
                name="community_post_category_latest",
            ),
        ]

    def __str__(self):
        return str(self.pk)


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    content = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=16, choices=ContentStatus.choices, default=ContentStatus.VISIBLE
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [("moderate_comment", "Can hide and restore comments")]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ContentStatus.values), name="community_comment_status"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="deleted", deleted_at__isnull=False, content="")
                    | (~Q(status="deleted") & Q(deleted_at__isnull=True))
                ),
                name="community_comment_deletion",
            ),
        ]
        indexes = [
            models.Index(
                fields=["post", "created_at", "id"],
                condition=Q(status="visible"),
                name="community_comment_order",
            )
        ]

    def __str__(self):
        return str(self.pk)


class Like(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="community_like_unique")
        ]


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", "스팸"
        ABUSE = "abuse", "괴롭힘"
        INAPPROPRIATE = "inappropriate", "부적절한 콘텐츠"
        OTHER = "other", "기타"

    class Status(models.TextChoices):
        PENDING = "pending", "미처리"
        RESOLVED = "resolved", "수용"
        DISMISSED = "dismissed", "기각"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="community_reports"
    )
    post = models.ForeignKey(Post, null=True, blank=True, on_delete=models.PROTECT)
    comment = models.ForeignKey(Comment, null=True, blank=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    details = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    snapshot_title = models.CharField(max_length=200, blank=True)
    snapshot_content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="community_reviews",
    )

    class Meta:
        permissions = [("review_report", "Can process reports")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(post__isnull=False, comment__isnull=True)
                    | Q(post__isnull=True, comment__isnull=False)
                ),
                name="community_report_target",
            ),
            models.UniqueConstraint(
                fields=["reporter", "post"],
                condition=Q(post__isnull=False),
                name="community_report_post_unique",
            ),
            models.UniqueConstraint(
                fields=["reporter", "comment"],
                condition=Q(comment__isnull=False),
                name="community_report_comment_unique",
            ),
            models.CheckConstraint(
                condition=Q(reason__in=["spam", "abuse", "inappropriate", "other"]),
                name="community_report_reason",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "resolved", "dismissed"]),
                name="community_report_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="pending", reviewed_at__isnull=True, reviewed_by__isnull=True)
                    | Q(
                        status__in=["resolved", "dismissed"],
                        reviewed_at__isnull=False,
                        reviewed_by__isnull=False,
                        snapshot_title="",
                        snapshot_content="",
                        details="",
                    )
                ),
                name="community_report_review",
            ),
        ]

    @property
    def target_type(self):
        return "post" if self.post_id else "comment"

    @property
    def target_id(self):
        return self.post_id or self.comment_id

    def __str__(self):
        return str(self.pk)
