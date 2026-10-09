from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from .models import Category, News, NewsCandidate, RawItem, Source
from .parser import CollectionError, canonicalize


class ReviewConflict(APIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "이미 처리되었거나 출처 정책과 일치하지 않습니다."


def require_source(source):
    if not source.is_active or not source.policy_checked_at:
        raise CollectionError("source_inactive_or_policy_unchecked")
    if source.adapter_key != "dreamnews_dretec":
        raise CollectionError("unsupported_adapter")


@transaction.atomic
def store_item(*, source_id, item):
    source = Source.objects.select_for_update(no_key=True).get(pk=source_id)
    require_source(source)
    if (
        canonicalize(item.canonical_url).rsplit("/", 1)[1] != item.external_id
        or not item.title
        or len(item.title) > 500
        or "ちいかわ" not in item.title
        or timezone.is_naive(item.published_at)
    ):
        raise CollectionError("invalid_normalized_item")
    matches = list(
        RawItem.objects.filter(source=source).filter(
            Q(external_id=item.external_id) | Q(canonical_url=item.canonical_url)
        )
    )
    if len(matches) > 1:
        raise CollectionError("identity_conflict")
    if matches:
        existing = matches[0]
        if existing.external_id != item.external_id or existing.canonical_url != item.canonical_url:
            raise CollectionError("identity_conflict")
        # Never update a prior snapshot, even if the metadata hash changed.
        return NewsCandidate.objects.get(raw_item=existing), False
    raw = RawItem.objects.create(
        source=source,
        external_id=item.external_id,
        canonical_url=item.canonical_url,
        title=item.title,
        published_at=item.published_at,
        metadata_hash=item.metadata_hash,
    )
    return NewsCandidate.objects.create(raw_item=raw, title=raw.title), True


@transaction.atomic
def review_candidate(*, user, candidate_id, action):
    if not (
        user.is_active
        and user.is_staff
        and user.has_perms(["news.view_newscandidate", "news.review_newscandidate"])
    ):
        raise PermissionDenied()
    candidate = get_object_or_404(
        NewsCandidate.objects.select_for_update(of=("self",), no_key=True).select_related(
            "raw_item__source"
        ),
        pk=candidate_id,
    )
    if action not in ("approve", "reject"):
        raise ReviewConflict()
    if candidate.status == NewsCandidate.Status.PUBLISHED and action == "approve":
        return News.objects.get(candidate=candidate)
    if candidate.status != NewsCandidate.Status.PENDING:
        raise ReviewConflict()
    raw = candidate.raw_item
    if (
        raw.source.adapter_key != "dreamnews_dretec"
        or candidate.title != raw.title
        or candidate.category != Category.GOODS
        or candidate.summary
    ):
        raise ReviewConflict()
    result = None
    if action == "approve":
        result = News.objects.create(
            candidate=candidate,
            source=raw.source,
            source_url=raw.canonical_url,
            title=candidate.title,
            category=candidate.category,
            summary="",
            published_at=raw.published_at,
        )
    candidate.status = "published" if action == "approve" else "rejected"
    candidate.reviewed_by, candidate.reviewed_at = user, timezone.now()
    candidate.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[candidate],
        action_flag=CHANGE,
        change_message=action,
        single_object=True,
    )
    return result
