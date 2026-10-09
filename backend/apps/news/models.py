import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

DREAMNEWS_LIST = "https://www.dreamnews.jp/company/0000014066/"
DREAMNEWS_POLICY = "https://www.dreamnews.jp/sitepolicy"


class Category(models.TextChoices):
    NEWS = "news", "정보"
    GOODS = "goods", "굿즈"
    EVENT = "event", "이벤트"
    COLLABORATION = "collaboration", "콜라보"


class Source(models.Model):
    class Type(models.TextChoices):
        OFFICIAL = "official", "공식"
        GOODS = "goods", "굿즈"
        EVENT = "event", "이벤트"
        COLLABORATION = "collaboration", "콜라보"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=Type.choices, default=Type.GOODS)
    adapter_key = models.CharField(
        max_length=40,
        choices=[("dreamnews_dretec", "DreamNews / 드리텍")],
        default="dreamnews_dretec",
        unique=True,
    )
    base_url = models.URLField(max_length=500, default=DREAMNEWS_LIST)
    is_active = models.BooleanField(default=False)
    policy_url = models.URLField(max_length=500, default=DREAMNEWS_POLICY)
    policy_checked_at = models.DateTimeField(null=True, blank=True)
    policy_notes = models.TextField(blank=True)
    next_request_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(source_type__in=["official", "goods", "event", "collaboration"]),
                name="news_source_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    adapter_key="dreamnews_dretec",
                    base_url=DREAMNEWS_LIST,
                    policy_url=DREAMNEWS_POLICY,
                ),
                name="news_source_adapter",
            ),
            models.CheckConstraint(
                condition=Q(is_active=False) | Q(policy_checked_at__isnull=False),
                name="news_source_policy_checked",
            ),
        ]

    def clean(self):
        if self.base_url != DREAMNEWS_LIST or self.policy_url != DREAMNEWS_POLICY:
            raise ValidationError("등록된 출처 URL만 사용할 수 있습니다.")
        if self.is_active and not self.policy_checked_at:
            raise ValidationError("활성화 전에 이용 정책을 확인하세요.")

    def __str__(self):
        return self.code


class RawItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=100)
    canonical_url = models.URLField(max_length=500)
    title = models.CharField(max_length=500)
    published_at = models.DateTimeField()
    collected_at = models.DateTimeField(auto_now_add=True)
    metadata_hash = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="news_raw_external_unique"
            ),
            models.UniqueConstraint(fields=["source", "canonical_url"], name="news_raw_url_unique"),
        ]

    def __str__(self):
        return str(self.pk)


class NewsCandidate(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "검수 대기"
        PUBLISHED = "published", "발행"
        REJECTED = "rejected", "반려"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_item = models.OneToOneField(RawItem, on_delete=models.PROTECT, related_name="candidate")
    title = models.CharField(max_length=500)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GOODS)
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [("review_newscandidate", "Can review news candidates")]
        constraints = [
            models.CheckConstraint(
                condition=Q(category__in=Category.values), name="news_candidate_category"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="pending", reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | Q(
                        status__in=["published", "rejected"],
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                    )
                ),
                name="news_candidate_review_state",
            ),
        ]

    def __str__(self):
        return str(self.pk)


class News(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.OneToOneField(NewsCandidate, on_delete=models.PROTECT, related_name="news")
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    source_url = models.URLField(max_length=500)
    title = models.CharField(max_length=500)
    category = models.CharField(max_length=20, choices=Category.choices)
    summary = models.TextField(blank=True)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "news"
        constraints = [
            models.CheckConstraint(condition=Q(category__in=Category.values), name="news_category")
        ]
        indexes = [
            models.Index(fields=["-published_at", "-id"], name="news_latest"),
            models.Index(fields=["category", "-published_at", "-id"], name="news_category_latest"),
        ]

    def __str__(self):
        return str(self.pk)
