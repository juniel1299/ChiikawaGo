from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction

from apps.news import crawler, services
from apps.news.models import News, NewsCandidate, RawItem
from apps.news.parser import CollectionError, parse_detail, parse_listing

pytestmark = pytest.mark.django_db
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/news"
URL = "https://www.dreamnews.jp/press/0000000001"


def test_parser_minimum_metadata():
    assert parse_listing((FIXTURES / "list.html").read_text()) == [URL]
    news_item = parse_detail((FIXTURES / "detail.html").read_text(), URL + "/")
    assert news_item.external_id == "0000000001"
    assert news_item.published_at == datetime(2026, 10, 1, 2, tzinfo=UTC)
    assert len(news_item.metadata_hash) == 64
    assert "body" not in news_item.__dict__


@pytest.mark.parametrize(
    "old,new",
    [
        ('"identifier":"0000000001"', '"identifier":"0000000009"'),
        ('"datePublished":"2026-10-01T11:00:00+09:00"', '"datePublished":"invalid"'),
        ('"datePublished":"2026-10-01T11:00:00+09:00"', '"datePublished":"2026-10-01T11:00:00"'),
        ('rel="canonical"', 'rel="other"'),
        ('"headline":"ちいかわ テスト商品"', '"headline":"wrong"'),
        ('"name":"株式会社ドリテック"', '"name":"other"'),
        ("application/ld+json", "application/json"),
    ],
)
def test_parser_rejects_missing_or_conflicting_metadata(old, new):
    with pytest.raises(CollectionError):
        parse_detail((FIXTURES / "detail.html").read_text().replace(old, new), URL)


def test_listing_limits_and_structure():
    html = (FIXTURES / "list.html").read_text()
    assert (
        len(parse_listing("".join(html.replace("0000000001", f"{n:010}") for n in range(10)))) == 5
    )
    with pytest.raises(CollectionError):
        parse_listing("<html>Challenge page</html>")
    assert parse_listing(html.replace("ちいかわ", "other")) == []


@pytest.mark.parametrize("state", ["pending", "published", "rejected"])
def test_recrawl_never_changes_snapshot(news_source, news_item, news_candidate, moderator, state):
    if state != "pending":
        services.review_candidate(
            user=moderator,
            candidate_id=news_candidate.pk,
            action="approve" if state == "published" else "reject",
        )
    raw_before = RawItem.objects.values().get()
    candidate_before = NewsCandidate.objects.values().get()
    news_before = list(News.objects.values())
    duplicate, created = services.store_item(
        source_id=news_source.pk,
        item=replace(
            news_item,
            title="ちいかわ 変更された商品",
            published_at=news_item.published_at + timedelta(days=1),
        ),
    )
    assert not created and duplicate.pk == news_candidate.pk
    assert RawItem.objects.values().get() == raw_before
    assert NewsCandidate.objects.values().get() == candidate_before
    assert list(News.objects.values()) == news_before


def test_review_lifecycle(news_candidate, moderator, other_user):
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.review_candidate(user=other_user, candidate_id=news_candidate.pk, action="approve")
    first = services.review_candidate(
        user=moderator, candidate_id=news_candidate.pk, action="approve"
    )
    second = services.review_candidate(
        user=moderator, candidate_id=news_candidate.pk, action="approve"
    )
    assert first.pk == second.pk and News.objects.count() == 1
    news_candidate.refresh_from_db()
    assert news_candidate.status == "published" and news_candidate.reviewed_by == moderator
    with pytest.raises(services.ReviewConflict):
        services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="reject")


@pytest.mark.parametrize(
    "field,value", [("title", "modified"), ("category", "event"), ("summary", "text")]
)
def test_source_policy_enforced_on_approval(news_candidate, moderator, field, value):
    NewsCandidate.objects.filter(pk=news_candidate.pk).update(**{field: value})
    with pytest.raises(services.ReviewConflict):
        services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="approve")
    assert not News.objects.exists()


@pytest.mark.parametrize("stage", ["raw_after", "candidate_after"])
def test_ingest_rollback(news_source, news_item, monkeypatch, stage):
    model = RawItem if stage == "raw_after" else NewsCandidate
    original = model.save

    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("injected")

    monkeypatch.setattr(model, "save", fail)
    with pytest.raises(RuntimeError):
        services.store_item(source_id=news_source.pk, item=news_item)
    assert not RawItem.objects.exists() and not NewsCandidate.objects.exists()


@pytest.mark.parametrize("stage", ["news_before", "news_after", "candidate_after", "audit_after"])
def test_publish_rollback(news_candidate, moderator, monkeypatch, stage):
    from django.contrib.admin.models import LogEntry

    model = (
        News
        if stage.startswith("news")
        else NewsCandidate
        if stage == "candidate_after"
        else LogEntry
    )
    original = model.save

    def fail(self, *args, **kwargs):
        if stage != "news_before":
            original(self, *args, **kwargs)
        raise RuntimeError("injected")

    monkeypatch.setattr(model, "save", fail)
    with pytest.raises(RuntimeError):
        services.review_candidate(user=moderator, candidate_id=news_candidate.pk, action="approve")
    news_candidate.refresh_from_db()
    assert news_candidate.status == "pending" and news_candidate.reviewed_at is None
    assert not News.objects.exists() and not LogEntry.objects.exists()


def test_database_constraints(news_candidate, moderator):
    raw = news_candidate.raw_item
    with pytest.raises(IntegrityError), transaction.atomic():
        RawItem.objects.create(
            source=raw.source,
            external_id=raw.external_id,
            canonical_url=raw.canonical_url + "/",
            title=raw.title,
            published_at=raw.published_at,
            metadata_hash=raw.metadata_hash,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        RawItem.objects.create(
            source=raw.source,
            external_id="different",
            canonical_url=raw.canonical_url,
            title=raw.title,
            published_at=raw.published_at,
            metadata_hash=raw.metadata_hash,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        NewsCandidate.objects.create(raw_item=raw, title=raw.title)
    with pytest.raises(IntegrityError), transaction.atomic():
        NewsCandidate.objects.filter(pk=news_candidate.pk).update(status="published")
    with pytest.raises(IntegrityError), transaction.atomic():
        NewsCandidate.objects.filter(pk=news_candidate.pk).update(category="invalid")
    news = services.review_candidate(
        user=moderator, candidate_id=news_candidate.pk, action="approve"
    )
    news.pk = None
    with pytest.raises(IntegrityError), transaction.atomic():
        news.save(force_insert=True)


def test_identity_conflict(news_source, news_item, news_candidate):
    RawItem.objects.filter(pk=news_candidate.raw_item_id).update(canonical_url=URL + "9")
    RawItem.objects.create(
        source=news_source,
        external_id="other",
        canonical_url=URL,
        title=news_item.title,
        published_at=news_item.published_at,
        metadata_hash=news_item.metadata_hash,
    )
    with pytest.raises(CollectionError, match="identity_conflict"):
        services.store_item(source_id=news_source.pk, item=news_item)
    assert NewsCandidate.objects.count() == 1


def test_fixture_pipeline_command_to_public_api(news_source, moderator, client):
    responses = {
        crawler.ROBOTS_URL: "User-agent: *\nDisallow:\n",
        crawler.DREAMNEWS_LIST: (FIXTURES / "list.html").read_text(),
        URL: (FIXTURES / "detail.html").read_text(),
    }
    with patch.object(crawler, "fetch", side_effect=lambda source_id, url, **kw: responses[url]):
        out = StringIO()
        call_command("collect_news", source=news_source.code, stdout=out)
        assert "created=1 skipped=0 failed=0" in out.getvalue()
        assert client.get("/api/v1/news").json()["count"] == 0
        c = NewsCandidate.objects.get()
        news = services.review_candidate(user=moderator, candidate_id=c.pk, action="approve")
        assert client.get(f"/api/v1/news/{news.pk}").json()["title"] == c.title
        out = StringIO()
        call_command("collect_news", source=news_source.code, stdout=out)
        assert "created=0 skipped=1 failed=0" in out.getvalue()
    assert client.get("/api/v1/news").json()["count"] == 1


def test_partial_collection_failure_preserves_success(news_source):
    listing = (FIXTURES / "list.html").read_text()
    listing += listing.replace("0000000001", "0000000004")
    responses = {
        crawler.ROBOTS_URL: "User-agent: *\nDisallow:\n",
        crawler.DREAMNEWS_LIST: listing,
        URL: (FIXTURES / "detail.html").read_text(),
    }
    with patch.object(
        crawler,
        "fetch",
        side_effect=lambda source_id, url, **kw: responses.get(url, "<html>invalid</html>"),
    ):
        with pytest.raises(CommandError):
            call_command("collect_news", source=news_source.code, stdout=StringIO())
    assert NewsCandidate.objects.count() == 1


def test_inactive_source(news_source, news_item):
    news_source.is_active = False
    news_source.save()
    with pytest.raises(CollectionError):
        services.store_item(source_id=news_source.pk, item=news_item)
    with patch.object(crawler, "fetch") as fetch, pytest.raises(CommandError):
        call_command("collect_news", source=news_source.code)
    fetch.assert_not_called()
