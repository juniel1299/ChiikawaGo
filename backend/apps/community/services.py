from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from .models import Comment, ContentStatus, Like, Post, Report
from .permissions import require_operator


class ModerationConflict(APIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "이미 삭제되었거나 처리된 데이터입니다."


def lock_post(post_id):
    return get_object_or_404(Post.objects.select_for_update(no_key=True), pk=post_id)


def lock_comment(comment_id):
    post_id = get_object_or_404(Comment.objects.only("post_id"), pk=comment_id).post_id
    post = lock_post(post_id)
    comment = get_object_or_404(Comment.objects.select_for_update(no_key=True), pk=comment_id)
    return post, comment


def require_visible(*objects):
    if any(obj.status != ContentStatus.VISIBLE for obj in objects):
        raise NotFound()


def require_owner(obj, user, *, parent=None):
    if obj.author_id != user.pk:
        require_visible(obj, *([parent] if parent else []))
        raise PermissionDenied()


@transaction.atomic
def create_post(*, user, **data):
    return Post.objects.create(author=user, **data)


@transaction.atomic
def update_post(*, user, post_id, data):
    post = lock_post(post_id)
    require_visible(post)
    require_owner(post, user)
    for key, value in data.items():
        setattr(post, key, value)
    post.save()
    return post


@transaction.atomic
def delete_post(*, user, post_id):
    post = lock_post(post_id)
    require_owner(post, user)
    if post.status == ContentStatus.DELETED:
        return
    now = timezone.now()
    Comment.objects.filter(post=post).exclude(status=ContentStatus.DELETED).update(
        status=ContentStatus.DELETED, content="", deleted_at=now, updated_at=now
    )
    Like.objects.filter(post=post).delete()
    post.status, post.deleted_at, post.title, post.content = ContentStatus.DELETED, now, "", ""
    post.save()


@transaction.atomic
def create_comment(*, user, post_id, content):
    post = lock_post(post_id)
    require_visible(post)
    return Comment.objects.create(post=post, author=user, content=content)


@transaction.atomic
def update_comment(*, user, comment_id, data):
    post, comment = lock_comment(comment_id)
    require_visible(post, comment)
    require_owner(comment, user, parent=post)
    for key, value in data.items():
        setattr(comment, key, value)
    comment.save()
    return comment


@transaction.atomic
def delete_comment(*, user, comment_id):
    post, comment = lock_comment(comment_id)
    require_owner(comment, user, parent=post)
    if comment.status == ContentStatus.DELETED:
        return
    comment.status, comment.content, comment.deleted_at = ContentStatus.DELETED, "", timezone.now()
    comment.save()


@transaction.atomic
def set_like(*, user, post_id, liked):
    post = lock_post(post_id)
    if liked:
        require_visible(post)
        Like.objects.get_or_create(user=user, post=post)
    else:
        Like.objects.filter(user=user, post=post).delete()


@transaction.atomic
def create_report(*, user, target_type, target_id, reason, details=""):
    if target_type == "post":
        post = target = lock_post(target_id)
    else:
        post, target = lock_comment(target_id)
    lookup = {target_type: target, "reporter": user}
    existing = Report.objects.filter(**lookup).first()
    if existing:
        return existing, False
    require_visible(post, target)
    if target.author_id == user.pk:
        raise ValidationError(
            {"reason": "self_report", "detail": "본인 콘텐츠는 신고할 수 없습니다."}
        )
    return Report.objects.create(
        **lookup,
        reason=reason,
        details=details,
        snapshot_title=target.title if target_type == "post" else "",
        snapshot_content=target.content,
    ), True


def record_action(*, user, obj, action):
    # Keep user content and report evidence out of the immutable admin audit log.
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[obj],
        action_flag=CHANGE,
        change_message=action,
        single_object=True,
    )


@transaction.atomic
def moderate_content(*, user, target_type, target_id, hidden):
    require_operator(user, f"community.view_{target_type}", f"community.moderate_{target_type}")
    if target_type == "post":
        target = lock_post(target_id)
    else:
        _, target = lock_comment(target_id)
    if target.status == ContentStatus.DELETED:
        raise ModerationConflict()
    target.status = ContentStatus.HIDDEN if hidden else ContentStatus.VISIBLE
    target.save(update_fields=["status", "updated_at"])
    record_action(user=user, obj=target, action="hide" if hidden else "restore")
    return target


@transaction.atomic
def review_report(*, user, report_id, status):
    require_operator(user, "community.view_report", "community.review_report")
    if status not in (Report.Status.RESOLVED, Report.Status.DISMISSED):
        raise ValidationError("잘못된 처리 상태입니다.")
    reference = get_object_or_404(Report, pk=report_id)
    if status == Report.Status.RESOLVED:
        require_operator(
            user,
            f"community.view_{reference.target_type}",
            f"community.moderate_{reference.target_type}",
        )
    if reference.post_id:
        target = lock_post(reference.post_id)
    else:
        _, target = lock_comment(reference.comment_id)
    report = Report.objects.select_for_update(no_key=True).get(pk=report_id)
    if report.status != Report.Status.PENDING:
        raise ModerationConflict()
    if status == Report.Status.RESOLVED and target.status != ContentStatus.DELETED:
        target.status = ContentStatus.HIDDEN
        target.save(update_fields=["status", "updated_at"])
        record_action(user=user, obj=target, action="hide: report resolved")
    report.status, report.reviewed_at, report.reviewed_by = status, timezone.now(), user
    report.snapshot_title = report.snapshot_content = report.details = ""
    report.save()
    record_action(user=user, obj=report, action=status)
    return report
