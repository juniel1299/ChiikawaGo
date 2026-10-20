import uuid
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.community import services
from apps.community.models import Comment, Like, Post, Report

pytestmark = pytest.mark.django_db
BASE = "/api/v1/community"


def test_post_jwt_crud_public_and_permissions(client, user, other_user):
    data = {"category": "free", "title": "제목", "content": "<script>plain text</script>"}
    assert client.post(f"{BASE}/posts", data, format="json").status_code == 401
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    response = client.post(f"{BASE}/posts", data, format="json")
    assert response.status_code == 201
    pk = response.data["id"]
    url = f"{BASE}/posts/{pk}"
    assert response.data["author"] == {"id": str(user.pk), "display_name": user.display_name}
    assert client.patch(url, {"title": "수정"}, format="json").status_code == 200
    client.credentials()
    assert client.get(url).data["title"] == "수정"
    assert client.get(f"{BASE}/posts").data["count"] == 1
    client.force_authenticate(other_user)
    assert client.patch(url, {"title": "위조"}, format="json").status_code == 403
    assert client.delete(url).status_code == 403
    client.force_authenticate(user)
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    post = Post.objects.get(pk=pk)
    assert post.title == post.content == ""
    assert post.deleted_at and post.status == "deleted"


@pytest.mark.parametrize(
    "data",
    [
        {"category": "unknown", "title": "t", "content": "c"},
        {"category": "free", "title": "  ", "content": "c"},
        {"category": "free", "title": "t", "content": "x" * 10001},
        {"category": "free", "title": "t", "content": "c", "status": "visible"},
        [],
        "invalid",
    ],
)
def test_post_invalid(authenticated, data):
    assert authenticated.post(f"{BASE}/posts", data, format="json").status_code == 400
    assert not Post.objects.exists()


def test_list_filter_order_counts_and_no_n_plus_one(
    client, user, other_user, django_assert_num_queries
):
    now = timezone.now()
    rows = [
        Post.objects.create(
            author=user, category="free" if i < 3 else "goods", title=str(i), content="c"
        )
        for i in range(5)
    ]
    Post.objects.update(created_at=now)
    Like.objects.create(user=user, post=rows[0])
    Like.objects.create(user=other_user, post=rows[0])
    for _ in range(3):
        Comment.objects.create(author=user, post=rows[0], content="c")
    Comment.objects.create(author=user, post=rows[0], content="hidden", status="hidden")
    with django_assert_num_queries(2):
        small = client.get(f"{BASE}/posts?page_size=1")
    with django_assert_num_queries(2):
        large = client.get(f"{BASE}/posts?page_size=100")
    assert small.data["next"] and large.data["count"] == 5
    assert [x["id"] for x in large.data["results"]] == sorted(
        [str(x.pk) for x in rows], reverse=True
    )
    item = next(x for x in large.data["results"] if x["id"] == str(rows[0].pk))
    assert (item["like_count"], item["comment_count"], item["is_liked"]) == (2, 3, False)
    assert "content" not in item and "email" not in item["author"]
    assert client.get(f"{BASE}/posts?category=free").data["count"] == 3
    assert client.get(f"{BASE}/posts?category=invalid").status_code == 400
    assert client.get(f"{BASE}/posts?page=999").status_code == 404
    client.force_authenticate(user)
    assert client.get(f"{BASE}/posts/{rows[0].pk}").data["is_liked"]


def test_comments_and_hidden_parent(client, user, other_user, community_post, moderator):
    url = f"{BASE}/posts/{community_post.pk}/comments"
    assert client.get(url).status_code == 200
    client.force_authenticate(other_user)
    result = client.post(url, {"content": "댓글"}, format="json")
    assert result.status_code == 201
    detail = f"{BASE}/comments/{result.data['id']}"
    assert client.patch(detail, {"content": "수정"}, format="json").status_code == 200
    client.force_authenticate(user)
    assert client.patch(detail, {"content": "위조"}, format="json").status_code == 403
    assert client.delete(detail).status_code == 403
    services.moderate_content(
        user=moderator, target_type="post", target_id=community_post.pk, hidden=True
    )
    client.force_authenticate(other_user)
    assert client.get(url).status_code == 404
    assert client.post(url, {"content": "c"}, format="json").status_code == 404
    assert client.patch(detail, {"content": "c"}, format="json").status_code == 404
    assert client.delete(detail).status_code == 204
    assert client.delete(detail).status_code == 204
    assert Comment.objects.get().content == ""


def test_comment_order_and_constant_queries(
    client, community_post, user, django_assert_num_queries
):
    rows = [
        Comment.objects.create(post=community_post, author=user, content=str(i)) for i in range(4)
    ]
    Comment.objects.update(created_at=timezone.now())
    url = f"{BASE}/posts/{community_post.pk}/comments"
    with django_assert_num_queries(3):
        client.get(url + "?page_size=1")
    with django_assert_num_queries(3):
        result = client.get(url)
    assert [x["id"] for x in result.data["results"]] == sorted(str(x.pk) for x in rows)


def test_like_idempotent_and_users(authenticated, user, other_user, community_post):
    url = f"{BASE}/posts/{community_post.pk}/like"
    for _ in range(2):
        response = authenticated.put(url, {}, format="json")
        assert response.status_code == 204 and response.content == b""
    assert Like.objects.count() == 1
    authenticated.force_authenticate(other_user)
    assert authenticated.put(url).status_code == 204
    assert Like.objects.count() == 2
    for _ in range(2):
        assert authenticated.delete(url).status_code == 204
    assert Like.objects.get().user == user
    assert authenticated.put(url, {"liked": True}, format="json").status_code == 400
    Post.objects.filter(pk=community_post.pk).update(status="hidden")
    assert authenticated.put(url).status_code == 404
    authenticated.force_authenticate(user)
    assert authenticated.delete(url).status_code == 204


@pytest.mark.parametrize("target_type", ["post", "comment"])
def test_report_snapshot_duplicate_and_purge(
    client, user, other_user, community_post, moderator, target_type
):
    target = (
        community_post
        if target_type == "post"
        else Comment.objects.create(post=community_post, author=user, content="원문")
    )
    client.force_authenticate(other_user)
    payload = {
        "target_type": target_type,
        "target_id": str(target.pk),
        "reason": "abuse",
        "details": "증거 설명",
    }
    first = client.post(f"{BASE}/reports", payload, format="json")
    assert first.status_code == 201
    report = Report.objects.get()
    assert report.snapshot_content == target.content
    if target_type == "post":
        services.delete_post(user=user, post_id=target.pk)
    else:
        services.delete_comment(user=user, comment_id=target.pk)
    duplicate = client.post(f"{BASE}/reports", {**payload, "reason": "spam"}, format="json")
    assert duplicate.status_code == 200 and duplicate.data == first.data
    report.refresh_from_db()
    assert report.snapshot_content and report.reason == "abuse"
    services.review_report(user=moderator, report_id=report.pk, status="resolved")
    report.refresh_from_db()
    assert report.status == "resolved" and report.reviewed_by == moderator
    assert report.snapshot_title == report.snapshot_content == report.details == ""
    assert client.post(f"{BASE}/reports", payload, format="json").status_code == 200
    assert Report.objects.count() == 1
    with pytest.raises(services.ModerationConflict):
        services.review_report(user=moderator, report_id=report.pk, status="dismissed")


def test_report_self_invalid_targets(authenticated, user, community_post):
    data = {"target_type": "post", "target_id": str(community_post.pk), "reason": "spam"}
    response = authenticated.post(f"{BASE}/reports", data, format="json")
    assert response.status_code == 400
    assert response.data["error"]["details"]["reason"] == "self_report"
    data["target_id"] = str(uuid.uuid4())
    assert authenticated.post(f"{BASE}/reports", data, format="json").status_code == 404
    assert not Report.objects.exists()


def test_delete_cascade_evidence_and_rollback(user, other_user, community_post):
    comment = Comment.objects.create(post=community_post, author=other_user, content="comment")
    Like.objects.create(post=community_post, user=user)
    report, _ = services.create_report(
        user=other_user, target_type="post", target_id=community_post.pk, reason="spam"
    )
    with (
        patch.object(Post, "save", side_effect=RuntimeError("failure")),
        pytest.raises(RuntimeError),
    ):
        services.delete_post(user=user, post_id=community_post.pk)
    comment.refresh_from_db()
    assert comment.content == "comment" and Like.objects.count() == 1
    services.delete_post(user=user, post_id=community_post.pk)
    comment.refresh_from_db()
    report.refresh_from_db()
    assert comment.status == "deleted" and comment.content == ""
    assert not Like.objects.exists() and report.snapshot_content == "본문"


@pytest.mark.parametrize("after_save", [False, True])
def test_review_rollback(moderator, other_user, community_post, after_save):
    report, _ = services.create_report(
        user=other_user,
        target_type="post",
        target_id=community_post.pk,
        reason="abuse",
        details="evidence",
    )
    original = Report.save

    def fail(self, *args, **kwargs):
        if after_save:
            original(self, *args, **kwargs)
        raise RuntimeError("failure")

    with patch.object(Report, "save", fail), pytest.raises(RuntimeError):
        services.review_report(user=moderator, report_id=report.pk, status="resolved")
    report.refresh_from_db()
    community_post.refresh_from_db()
    assert community_post.status == "visible"
    assert report.status == "pending" and report.details == "evidence" and report.snapshot_content


@pytest.mark.parametrize(
    "case",
    ["like", "report_duplicate", "report_none", "report_both", "category", "status", "purge"],
)
def test_db_constraints(user, other_user, community_post, case):
    comment = Comment.objects.create(author=user, post=community_post, content="c")
    Like.objects.create(user=user, post=community_post)
    report, _ = services.create_report(
        user=other_user, target_type="post", target_id=community_post.pk, reason="other"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        if case == "like":
            Like.objects.create(user=user, post=community_post)
        elif case == "report_duplicate":
            Report.objects.create(reporter=other_user, post=community_post, reason="other")
        elif case == "report_none":
            Report.objects.create(reporter=user, reason="other")
        elif case == "report_both":
            Report.objects.create(
                reporter=user, post=community_post, comment=comment, reason="other"
            )
        elif case in ("category", "status"):
            Post.objects.filter(pk=community_post.pk).update(**{case: "invalid"})
        else:
            Report.objects.filter(pk=report.pk).update(
                status="resolved", reviewed_at=timezone.now(), reviewed_by=user
            )


def test_inactive_user_and_anonymous_writes(client, user, community_post):
    token = str(RefreshToken.for_user(user).access_token)
    user.is_active = False
    user.save()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert (
        client.post(
            f"{BASE}/posts", {"category": "free", "title": "t", "content": "c"}, format="json"
        ).status_code
        == 401
    )
    client.credentials()
    for method, path in [
        ("post", f"/posts/{community_post.pk}/comments"),
        ("put", f"/posts/{community_post.pk}/like"),
        ("delete", f"/posts/{community_post.pk}/like"),
        ("post", "/reports"),
    ]:
        assert getattr(client, method)(BASE + path, {}, format="json").status_code == 401


@pytest.mark.parametrize("content", ["  ", "x" * 2001])
def test_invalid_comment_content(authenticated, community_post, content):
    assert (
        authenticated.post(
            f"{BASE}/posts/{community_post.pk}/comments", {"content": content}, format="json"
        ).status_code
        == 400
    )
    assert not Comment.objects.exists()


def test_report_hidden_target_and_no_content_in_logs(client, community_post, other_user, caplog):
    import logging

    client.force_authenticate(other_user)
    Post.objects.filter(pk=community_post.pk).update(content="PRIVATE-CONTENT-812", status="hidden")
    payload = {
        "target_type": "post",
        "target_id": str(community_post.pk),
        "reason": "spam",
        "details": "PRIVATE-EVIDENCE-812",
    }
    with caplog.at_level(logging.INFO, logger="chii.requests"):
        assert client.post(f"{BASE}/reports", payload, format="json").status_code == 404
        Post.objects.filter(pk=community_post.pk).update(status="visible")
        assert client.post(f"{BASE}/reports", payload, format="json").status_code == 201
    assert "PRIVATE-CONTENT-812" not in caplog.text
    assert "PRIVATE-EVIDENCE-812" not in caplog.text


def test_comment_report_unique_and_deleted_checks(user, other_user, community_post):
    comment = Comment.objects.create(post=community_post, author=user, content="c")
    Report.objects.create(reporter=other_user, comment=comment, reason="spam")
    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(reporter=other_user, comment=comment, reason="other")
    with pytest.raises(IntegrityError), transaction.atomic():
        Comment.objects.filter(pk=comment.pk).update(status="deleted", deleted_at=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        Post.objects.filter(pk=community_post.pk).update(
            status="deleted", deleted_at=timezone.now()
        )


def test_maximum_page_and_second_page(client, user):
    Post.objects.bulk_create(
        [Post(author=user, category="free", title=str(i), content="c") for i in range(105)]
    )
    first = client.get(BASE + "/posts?page_size=999")
    second = client.get(BASE + "/posts?page_size=100&page=2")
    assert len(first.data["results"]) == 100
    assert len(second.data["results"]) == 5
    assert not (
        {x["id"] for x in first.data["results"]} & {x["id"] for x in second.data["results"]}
    )
