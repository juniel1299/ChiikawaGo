from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import close_old_connections, connection, transaction
from rest_framework.test import APIClient

from apps.community import services
from apps.community.models import Comment, Like, Post, Report
from tests.integration.test_encounter_concurrency import run_overlapping

pytestmark = pytest.mark.django_db(transaction=True)
BASE = "/api/v1/community"


def request(user, method, path, data=None):
    client = APIClient()
    client.force_authenticate(user)
    return getattr(client, method)(BASE + path, data={} if data is None else data, format="json")


def pause_first_lock(monkeypatch):
    locked, release = Event(), Event()
    original = services.lock_post

    def lock(post_id):
        post = original(post_id)
        if not locked.is_set():
            locked.set()
            assert release.wait(10)
        return post

    monkeypatch.setattr(services, "lock_post", lock)
    return locked, release


@pytest.mark.parametrize("kind", ["like", "unlike", "report"])
def test_duplicate_requests_overlap(monkeypatch, community_post, other_user, kind):
    if kind == "unlike":
        Like.objects.create(post=community_post, user=other_user)
    locked, release = pause_first_lock(monkeypatch)
    path = f"/posts/{community_post.pk}/like"
    method, payload = ("delete" if kind == "unlike" else "put"), {}
    if kind == "report":
        path, method = "/reports", "post"
        payload = {"target_type": "post", "target_id": str(community_post.pk), "reason": "spam"}
    a, b = run_overlapping(
        lambda: request(other_user, method, path, payload),
        lambda: request(other_user, method, path, payload),
        locked,
        release,
    )
    if kind == "report":
        assert (a.status_code, b.status_code) == (201, 200)
        assert a.data == b.data and Report.objects.count() == 1
    else:
        assert a.status_code == b.status_code == 204
        assert Like.objects.count() == (1 if kind == "like" else 0)


@pytest.mark.parametrize("delete_first", [True, False])
def test_delete_and_comment_overlap(monkeypatch, community_post, user, other_user, delete_first):
    locked, release = pause_first_lock(monkeypatch)

    def delete():
        return request(user, "delete", f"/posts/{community_post.pk}")

    def create():
        return request(
            other_user, "post", f"/posts/{community_post.pk}/comments", {"content": "comment"}
        )

    a, b = run_overlapping(
        *((delete, create) if delete_first else (create, delete)), locked, release
    )
    assert (a.status_code, b.status_code) == ((204, 404) if delete_first else (201, 204))
    assert not Comment.objects.exclude(status="deleted").exists()
    assert not Comment.objects.exclude(content="").exists()


@pytest.mark.parametrize("edit_first", [True, False])
def test_edit_and_report_snapshot_overlap(
    monkeypatch, community_post, user, other_user, edit_first
):
    locked, release = pause_first_lock(monkeypatch)

    def edit():
        return request(user, "patch", f"/posts/{community_post.pk}", {"content": "new"})

    def report():
        return request(
            other_user,
            "post",
            "/reports",
            {"target_type": "post", "target_id": str(community_post.pk), "reason": "spam"},
        )

    a, b = run_overlapping(*((edit, report) if edit_first else (report, edit)), locked, release)
    assert sorted([a.status_code, b.status_code]) == [200, 201]
    assert Report.objects.get().snapshot_content == ("new" if edit_first else "본문")


@pytest.mark.parametrize("delete_first", [True, False])
def test_delete_and_review_overlap(
    monkeypatch, community_post, moderator, other_user, delete_first
):
    report, _ = services.create_report(
        user=other_user, target_type="post", target_id=community_post.pk, reason="spam"
    )
    locked, release = pause_first_lock(monkeypatch)

    def delete():
        return services.delete_post(user=moderator, post_id=community_post.pk)

    def review():
        return services.review_report(user=moderator, report_id=report.pk, status="resolved")

    run_overlapping(*((delete, review) if delete_first else (review, delete)), locked, release)
    report.refresh_from_db()
    community_post.refresh_from_db()
    assert report.status == "resolved" and report.snapshot_content == ""
    assert community_post.status == "deleted" and community_post.content == ""


def test_failed_report_does_not_leave_partial_state(monkeypatch, community_post, other_user):
    original = Report.save
    locked, release = Event(), Event()

    def save(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if not locked.is_set():
            locked.set()
            assert release.wait(10)
            raise RuntimeError("injected failure")

    monkeypatch.setattr(Report, "save", save)
    payload = {"target_type": "post", "target_id": str(community_post.pk), "reason": "spam"}
    a, b = run_overlapping(
        lambda: request(other_user, "post", "/reports", payload),
        lambda: request(other_user, "post", "/reports", payload),
        locked,
        release,
    )
    assert (a.status_code, b.status_code) == (500, 201)
    assert Report.objects.count() == 1


def test_different_post_independent(community_post, user):
    other = Post.objects.create(author=user, category="free", title="other", content="c")

    def run():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '3s'")
            return request(user, "put", f"/posts/{other.pk}/like")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Post.objects.select_for_update(no_key=True).get(pk=community_post.pk)
            assert pool.submit(run).result(timeout=5).status_code == 204
