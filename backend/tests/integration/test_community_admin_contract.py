import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import Client
from drf_spectacular.generators import SchemaGenerator

from apps.community import services
from apps.community.models import Comment, Post, Report
from tests.integration.test_capture_admin_contract import resolve

pytestmark = pytest.mark.django_db
BASE = "/api/v1/community"


def check(schema, spec, actual):
    spec = resolve(schema, spec)
    if not spec:  # The shared error details intentionally allow any JSON shape.
        return
    if actual is None:
        assert spec.get("nullable")
    elif isinstance(actual, dict):
        assert spec["type"] == "object"
        assert set(spec["properties"]) == set(actual)
        assert set(spec.get("required", [])) <= set(actual)
        for key, value in actual.items():
            check(schema, spec["properties"][key], value)
    elif isinstance(actual, list):
        assert spec["type"] == "array"
        for item in actual:
            check(schema, spec["items"], item)
    else:
        expected = (
            "boolean"
            if isinstance(actual, bool)
            else "integer"
            if isinstance(actual, int)
            else "string"
        )
        assert spec["type"] == expected
        if "enum" in spec:
            assert actual in spec["enum"]


def test_api_contract(authenticated, other_user):
    schema = SchemaGenerator().get_schema(public=True)

    def verify(path, method, response):
        operation = schema["paths"][BASE + path][method]
        spec = operation["responses"][str(response.status_code)]
        if response.status_code == 204:
            assert "content" not in spec and response.content == b""
        else:
            check(schema, spec["content"]["application/json"]["schema"], response.json())

    post = authenticated.post(
        BASE + "/posts", {"category": "free", "title": "t", "content": "c"}, format="json"
    )
    assert post.status_code == 201
    verify("/posts", "post", post)
    pk = post.data["id"]
    verify("/posts", "get", authenticated.get(BASE + "/posts"))
    verify("/posts/{id}", "get", authenticated.get(BASE + f"/posts/{pk}"))
    verify(
        "/posts/{id}",
        "patch",
        authenticated.patch(BASE + f"/posts/{pk}", {"title": "updated"}, format="json"),
    )
    comment = authenticated.post(BASE + f"/posts/{pk}/comments", {"content": "c"}, format="json")
    verify("/posts/{id}/comments", "post", comment)
    verify("/posts/{id}/comments", "get", authenticated.get(BASE + f"/posts/{pk}/comments"))
    cid = comment.data["id"]
    verify(
        "/comments/{id}",
        "patch",
        authenticated.patch(BASE + f"/comments/{cid}", {"content": "updated"}, format="json"),
    )
    for method in ("put", "delete"):
        verify(
            "/posts/{id}/like", method, getattr(authenticated, method)(BASE + f"/posts/{pk}/like")
        )
    verify("/comments/{id}", "delete", authenticated.delete(BASE + f"/comments/{cid}"))
    authenticated.force_authenticate(other_user)
    for status in (201, 200):
        report = authenticated.post(
            BASE + "/reports",
            {"target_type": "post", "target_id": pk, "reason": "spam"},
            format="json",
        )
        assert report.status_code == status
        verify("/reports", "post", report)
    # All item fields are required; nullable page links are the existing pagination exception.
    for name in ("PostDetail", "PostList", "Comment", "Report", "Author"):
        spec = schema["components"]["schemas"][name]
        assert set(spec["required"]) == set(spec["properties"])
    verify("/posts/{id}", "delete", authenticated.delete(BASE + f"/posts/{pk}"))  # 403 envelope


@pytest.mark.parametrize("model", [Post, Comment, Report])
def test_readonly_admin_even_superuser(client, moderator, other_user, community_post, model):
    if model is Comment:
        obj = Comment.objects.create(post=community_post, author=other_user, content="comment")
    elif model is Report:
        obj, _ = services.create_report(
            user=other_user, target_type="post", target_id=community_post.pk, reason="spam"
        )
    else:
        obj = community_post
    client.force_login(moderator)
    root = f"/admin/community/{model._meta.model_name}/"
    assert client.get(root).status_code == 200
    assert client.get(f"{root}{obj.pk}/change/").status_code == 200
    assert client.get(root + "add/").status_code == 403
    assert client.post(f"{root}{obj.pk}/change/", {"content": "overwrite"}).status_code == 403
    assert client.post(f"{root}{obj.pk}/delete/", {"post": "yes"}).status_code == 403


def test_admin_permissions_csrf_and_evidence(client, user, other_user, community_post):
    report, _ = services.create_report(
        user=other_user,
        target_type="post",
        target_id=community_post.pk,
        reason="spam",
        details="private evidence",
    )
    user.is_staff = True
    user.save()
    client.force_login(user)
    url = f"/admin/community/report/{report.pk}/moderate/"
    assert client.get(url).status_code == 403
    perms = Permission.objects.filter(
        content_type__app_label="community", codename__in=["view_report", "review_report"]
    )
    user.user_permissions.add(*perms)
    assert client.get(url).status_code == 200
    assert client.post(url, {"action": "resolved"}).status_code == 403
    assert client.post(url, {"action": "dismissed"}).status_code == 302
    report.refresh_from_db()
    community_post.refresh_from_db()
    assert report.snapshot_content == report.details == "" and community_post.status == "visible"
    assert not LogEntry.objects.filter(change_message__contains="private evidence").exists()
    assert client.post(url, {"action": "resolved"}).status_code == 403
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(user)
    assert csrf.post(url, {"action": "dismissed"}).status_code == 403


def test_moderation_restore_does_not_restore_child_or_deleted(client, moderator, community_post):
    comment = Comment.objects.create(
        post=community_post, author=moderator, content="private content"
    )
    client.force_login(moderator)
    post_url = f"/admin/community/post/{community_post.pk}/moderate/"
    comment_url = f"/admin/community/comment/{comment.pk}/moderate/"
    assert client.post(comment_url, {"action": "hide"}).status_code == 302
    assert client.post(post_url, {"action": "hide"}).status_code == 302
    assert client.post(post_url, {"action": "restore"}).status_code == 302
    comment.refresh_from_db()
    assert comment.status == "hidden"
    services.delete_post(user=moderator, post_id=community_post.pk)
    assert client.post(post_url, {"action": "restore"}).status_code == 409
    assert client.post(comment_url, {"action": "restore"}).status_code == 409
    assert not LogEntry.objects.filter(object_repr__contains="private content").exists()


def test_non_superuser_review_with_csrf(other_user, community_post, user):
    report, _ = services.create_report(
        user=other_user,
        target_type="post",
        target_id=community_post.pk,
        reason="abuse",
        details="secret",
    )
    user.is_staff = True
    user.save()
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="community",
            codename__in=["view_report", "review_report", "view_post", "moderate_post"],
        )
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    url = f"/admin/community/report/{report.pk}/moderate/"
    assert client.get(url).status_code == 200
    token = client.cookies["csrftoken"].value
    assert client.post(url, {"action": "resolved", "csrfmiddlewaretoken": token}).status_code == 302
    report.refresh_from_db()
    community_post.refresh_from_db()
    assert community_post.status == "hidden" and report.status == "resolved"
    assert report.details == report.snapshot_content == ""
    assert (
        client.post(url, {"action": "dismissed", "csrfmiddlewaretoken": token}).status_code == 409
    )
