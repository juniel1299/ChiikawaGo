from threading import Event

import pytest
from django.db import transaction

from apps.news import crawler, services
from apps.news.models import News, NewsCandidate, RawItem, Source
from tests.integration.test_encounter_concurrency import run_overlapping

pytestmark = pytest.mark.django_db(transaction=True)


def test_duplicate_ingest_waits_on_source(news_source, news_item, monkeypatch):
    locked, release = Event(), Event()
    original = RawItem.save

    def pause(self, *args, **kwargs):
        original(self, *args, **kwargs)
        locked.set()
        assert release.wait(10)

    monkeypatch.setattr(RawItem, "save", pause)

    def create():
        return services.store_item(source_id=news_source.pk, item=news_item)

    a, b = run_overlapping(create, create, locked, release)
    assert a[1] is True and b[1] is False and a[0].pk == b[0].pk
    assert RawItem.objects.count() == NewsCandidate.objects.count() == 1


@pytest.mark.parametrize(
    "first,second", [("approve", "approve"), ("approve", "reject"), ("reject", "approve")]
)
def test_review_race(news_candidate, moderator, monkeypatch, first, second):
    locked, release = Event(), Event()
    original = NewsCandidate.save

    def pause(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if not locked.is_set():
            locked.set()
            assert release.wait(10)

    monkeypatch.setattr(NewsCandidate, "save", pause)

    def review(action):
        try:
            news = services.review_candidate(
                user=moderator, candidate_id=news_candidate.pk, action=action
            )
            return news.pk if news else None
        except services.ReviewConflict:
            return "conflict"

    a, b = run_overlapping(lambda: review(first), lambda: review(second), locked, release)
    assert (b == a) if first == second else (b == "conflict")
    news_candidate.refresh_from_db()
    assert news_candidate.status == ("published" if first == "approve" else "rejected")
    assert News.objects.count() == (1 if first == "approve" else 0)


def test_failed_approval_rolls_back_before_waiting_retry(news_candidate, moderator, monkeypatch):
    locked, release = Event(), Event()
    original = News.save

    def fail_first(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if not locked.is_set():
            locked.set()
            assert release.wait(10)
            raise RuntimeError("injected")

    monkeypatch.setattr(News, "save", fail_first)

    def review():
        try:
            return services.review_candidate(
                user=moderator, candidate_id=news_candidate.pk, action="approve"
            )
        except RuntimeError:
            return None

    a, b = run_overlapping(review, review, locked, release)
    assert a is None and b is not None and News.objects.count() == 1


def test_request_reservation_serializes(news_source, monkeypatch):
    locked, release = Event(), Event()
    original = Source.save

    def pause(self, *args, **kwargs):
        original(self, *args, **kwargs)
        locked.set()
        assert release.wait(10)

    monkeypatch.setattr(Source, "save", pause)
    a, b = run_overlapping(
        lambda: crawler.reserve_request(news_source.pk),
        lambda: crawler.reserve_request(news_source.pk),
        locked,
        release,
    )
    assert a == 0 and 0 < b <= 10


def test_deactivation_rechecked_after_lock(news_source, news_item):
    locked, release = Event(), Event()

    def deactivate():
        with transaction.atomic():
            Source.objects.filter(pk=news_source.pk).update(is_active=False)
            locked.set()
            assert release.wait(10)

    def store():
        from apps.news.parser import CollectionError

        with pytest.raises(CollectionError):
            services.store_item(source_id=news_source.pk, item=news_item)

    run_overlapping(deactivate, store, locked, release)
    assert not RawItem.objects.exists()
