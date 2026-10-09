from dataclasses import replace

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import Client
from drf_spectacular.generators import SchemaGenerator

from apps.news import services
from apps.news.models import News, NewsCandidate, RawItem
from tests.integration.test_community_admin_contract import check

pytestmark = pytest.mark.django_db


def test_public_pagination_order_and_n_plus_one(
    news_source, news_item, moderator, client, django_assert_num_queries
):
    ids = []
    for number in range(25):
        external_id = f"{number:010}"
        news_candidate, _ = services.store_item(
            source_id=news_source.pk,
            item=replace(
                news_item,
                external_id=external_id,
                canonical_url=f"https://www.dreamnews.jp/press/{external_id}",
            ),
        )
        news = services.review_candidate(
            user=moderator, candidate_id=news_candidate.pk, action="approve"
        )
        ids.append(str(news.pk))
    news_source.is_active = False
    news_source.save()
    with django_assert_num_queries(2):
        response = client.get("/api/v1/news")
    data = response.json()
    assert data["count"] == 25 and len(data["results"]) == 20
    assert [row["id"] for row in data["results"]] == sorted(ids, reverse=True)[:20]
    assert len(client.get("/api/v1/news?page=2").json()["results"]) == 5
    assert client.get("/api/v1/news?page=3").status_code == 404
    assert len(client.get("/api/v1/news?page_size=1000").json()["results"]) == 25
    assert client.get("/api/v1/news?category=event").json()["count"] == 0
    assert client.get("/api/v1/news?category=goods").json()["count"] == 25
    assert client.get("/api/v1/news?category=invalid").status_code == 400
    with django_assert_num_queries(1):
        assert client.get(f"/api/v1/news/{ids[0]}").status_code == 200


def test_openapi_actual_contract(news_candidate, moderator, client):
    schema = SchemaGenerator().get_schema(public=True)
    assert client.get("/api/v1/news").json()["count"] == 0
    n = services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="approve")
    for template, url in [
        ("/api/v1/news", "/api/v1/news"),
        ("/api/v1/news/{id}", f"/api/v1/news/{n.pk}"),
    ]:
        response = client.get(url)
        assert response.status_code == 200
        spec = schema["paths"][template]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        check(schema, spec, response.json())
    for name in ("News", "NewsSource"):
        spec = schema["components"]["schemas"][name]
        assert set(spec["required"]) == set(spec["properties"])
    for url, status in [
        ("/api/v1/news?category=invalid", 400),
        ("/api/v1/news/00000000-0000-0000-0000-000000000001", 404),
    ]:
        r = client.get(url)
        assert r.status_code == status
        check(schema, {"$ref": "#/components/schemas/ApiError"}, r.json())
    assert client.post("/api/v1/news", {}).status_code == 405


@pytest.mark.parametrize("model", [RawItem, NewsCandidate, News])
def test_admin_readonly_even_superuser(news_candidate, moderator, client, model):
    news = services.review_candidate(
        user=moderator, candidate_id=news_candidate.pk, action="approve"
    )
    obj = (
        news_candidate.raw_item
        if model is RawItem
        else news_candidate
        if model is NewsCandidate
        else news
    )
    client.force_login(moderator)
    root = f"/admin/news/{model._meta.model_name}/"
    assert client.get(root).status_code == 200
    assert client.get(f"{root}{obj.pk}/change/").status_code == 200
    assert client.get(root + "add/").status_code == 403
    assert client.post(f"{root}{obj.pk}/change/", {"title": "modified"}).status_code == 403
    assert client.post(f"{root}{obj.pk}/delete/", {"post": "yes"}).status_code == 403


def test_admin_review_permissions_csrf(news_candidate, user):
    user.is_staff = True
    user.save()
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    url = f"/admin/news/newscandidate/{news_candidate.pk}/review/"
    assert client.get(url).status_code == 403
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="news",
            codename__in=["view_newscandidate", "review_newscandidate"],
        )
    )
    assert client.get(url).status_code == 200
    assert not News.objects.exists()
    assert client.post(url, {"action": "approve"}).status_code == 403
    token = client.cookies["csrftoken"].value
    assert client.post(url, {"action": "approve", "csrfmiddlewaretoken": token}).status_code == 302
    assert News.objects.count() == 1
    assert not LogEntry.objects.filter(object_repr__contains=news_candidate.title).exists()
    assert client.post(url, {"action": "reject", "csrfmiddlewaretoken": token}).status_code == 409


def test_source_requires_policy_check_and_fixed_adapter(news_source):
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction

    news_source.policy_checked_at = None
    with pytest.raises(ValidationError):
        news_source.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        news_source.save()
    news_source.refresh_from_db()
    news_source.base_url = "https://example.com/"
    with pytest.raises(ValidationError):
        news_source.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        news_source.save()


def test_rejected_and_inactive_reviewers_cannot_publish(news_candidate, moderator):
    from rest_framework.exceptions import PermissionDenied

    services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="reject")
    with pytest.raises(services.ReviewConflict):
        services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="approve")
    moderator.is_active = False
    moderator.save()
    with pytest.raises(PermissionDenied):
        services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="approve")
    assert not News.objects.exists()


def test_source_admin_edit_preserves_request_reservation(news_source, moderator):
    from datetime import timedelta

    from django.contrib import admin
    from django.test import RequestFactory
    from django.utils import timezone

    from apps.news.models import Source

    next_request = timezone.now() + timedelta(seconds=10)
    Source.objects.filter(pk=news_source.pk).update(next_request_at=next_request)
    news_source.name = "Updated display name"
    request = RequestFactory().post("/admin/news/source/")
    request.user = moderator
    admin.site._registry[Source].save_model(request, news_source, None, True)
    news_source.refresh_from_db()
    assert news_source.next_request_at == next_request
