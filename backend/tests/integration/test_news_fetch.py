from datetime import timedelta
from email.message import Message
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest
from django.db import connection
from django.utils import timezone

from apps.news import crawler
from apps.news.parser import CollectionError, validate_url
from tests.integration.test_news import URL

pytestmark = pytest.mark.django_db(transaction=True)


class Response(BytesIO):
    status = 200

    def __init__(self, data=b"<html></html>", content_type="text/html"):
        super().__init__(data)
        self.headers = Message()
        self.headers["Content-Type"] = content_type


@pytest.mark.parametrize(
    "url",
    [
        "http://www.dreamnews.jp/press/0000000001",
        "https://evil.test/press/0000000001",
        "https://www.dreamnews.jp@127.0.0.1/press/0000000001",
        "https://www.dreamnews.jp/press/0000000001?tracking=x",
        "https://www.dreamnews.jp/press/0000000001/images/bodyimage1",
        "https://www.dreamnews.jp/company/0000014066/?page=2",
        "https://www.dreamnews.jp:443/press/0000000001",
    ],
)
def test_only_registered_urls(url):
    with pytest.raises(CollectionError):
        validate_url(url)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "<html>challenge</html>",
        "User-agent: *\nDisallow: /*.pdf$",
        "User-agent: *\nCrawl-delay: 30",
        "User-agent: *\nUnknown: yes",
        "User-agent: *\nAllow: /\nDisallow: /private",
    ],
)
def test_unsupported_robots_fail_closed(text):
    with pytest.raises(CollectionError):
        crawler.parse_robots(text)


def test_supported_robots():
    assert crawler.parse_robots(
        "User-agent: *\nDisallow:\nSitemap: http://example.test/map"
    ).can_fetch(crawler.USER_AGENT, URL)
    assert not crawler.parse_robots("User-agent: *\nDisallow: /press/").can_fetch(
        crawler.USER_AGENT, URL
    )


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_failures_no_retry(news_source, monkeypatch, status):
    opener = Mock()
    opener.open.side_effect = HTTPError(URL, status, "private error body", Message(), None)
    monkeypatch.setattr(crawler, "build_opener", lambda *args: opener)
    with pytest.raises(CollectionError, match=f"http_{status}"):
        crawler.fetch(news_source.pk, URL)
    assert opener.open.call_count == 1


@pytest.mark.parametrize("error", [TimeoutError("private"), URLError("private")])
def test_fetch_errors_safe(news_source, monkeypatch, error):
    opener = Mock()
    opener.open.side_effect = error
    monkeypatch.setattr(crawler, "build_opener", lambda *args: opener)
    with pytest.raises(CollectionError, match="^fetch_failed$"):
        crawler.fetch(news_source.pk, URL)


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.test/",
        "https://www.dreamnews.jp/press/0000000002",
        "http://www.dreamnews.jp/press/0000000001",
    ],
)
def test_redirects_checked_before_fetch(news_source, monkeypatch, target):
    opener = Mock()
    headers = Message()
    headers["Location"] = target
    opener.open.side_effect = HTTPError(URL, 302, "redirect", headers, None)
    monkeypatch.setattr(crawler, "build_opener", lambda *args: opener)
    with pytest.raises(CollectionError):
        crawler.fetch(news_source.pk, URL)
    assert opener.open.call_count == 1


def test_canonical_redirect_and_network_outside_atomic(news_source, monkeypatch):
    headers = Message()
    headers["Location"] = URL
    responses = iter([HTTPError(URL + "/", 301, "redirect", headers, None), Response()])

    def open_request(request, timeout):
        assert not connection.in_atomic_block
        assert timeout == 10
        assert request.get_header("User-agent") == crawler.USER_AGENT
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(crawler, "build_opener", lambda *args: Mock(open=open_request))
    clock = [timezone.now()]
    monkeypatch.setattr(crawler.timezone, "now", lambda: clock[0])

    def sleep(delay):
        assert not connection.in_atomic_block and delay == 10
        clock[0] += timedelta(seconds=delay)

    monkeypatch.setattr(crawler.time, "sleep", sleep)
    assert crawler.fetch(news_source.pk, URL + "/") == "<html></html>"
    news_source.refresh_from_db()
    assert news_source.next_request_at == clock[0] + timedelta(seconds=10)


@pytest.mark.parametrize("kind", ["size", "type", "encoding", "challenge"])
def test_response_limits(news_source, monkeypatch, kind):
    response = Response(
        b"x" * (crawler.MAX_BYTES + 1) if kind == "size" else b"ok",
        "application/json" if kind == "type" else "text/html",
    )
    if kind == "encoding":
        response.headers["Content-Encoding"] = "gzip"
    if kind == "challenge":
        response.headers["cf-mitigated"] = "challenge"
    monkeypatch.setattr(
        crawler, "build_opener", lambda *args: Mock(open=Mock(return_value=response))
    )
    with pytest.raises(CollectionError):
        crawler.fetch(news_source.pk, URL)


def test_robots_disallow_makes_no_request(news_source, monkeypatch):
    opener = Mock()
    monkeypatch.setattr(crawler, "build_opener", lambda *args: opener)
    with pytest.raises(CollectionError, match="robots_denied"):
        crawler.fetch(
            news_source.pk, URL, robots=crawler.parse_robots("User-agent: *\nDisallow: /")
        )
    opener.open.assert_not_called()


def test_fixed_http_pipeline_to_review_and_public_api(news_source, moderator, client, monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    from apps.news.models import News, NewsCandidate
    from apps.news.services import review_candidate
    from tests.integration.test_news import FIXTURES

    payloads = {
        crawler.ROBOTS_URL: ("User-agent: *\nDisallow:\n", "text/plain"),
        crawler.DREAMNEWS_LIST: ((FIXTURES / "list.html").read_text(), "text/html"),
        URL: ((FIXTURES / "detail.html").read_text(), "text/html"),
    }
    requested = []
    clock = [timezone.now()]
    monkeypatch.setattr(crawler.timezone, "now", lambda: clock[0])

    def sleep(delay):
        assert not connection.in_atomic_block
        clock[0] += timedelta(seconds=delay)

    def open_request(request, timeout):
        assert not connection.in_atomic_block
        requested.append((request.full_url, clock[0]))
        text, content_type = payloads[request.full_url]
        return Response(text.encode(), content_type)

    monkeypatch.setattr(crawler.time, "sleep", sleep)
    monkeypatch.setattr(crawler, "build_opener", lambda *args: Mock(open=open_request))
    call_command("collect_news", source=news_source.code, stdout=StringIO())
    assert [url for url, _ in requested] == list(payloads)
    assert all(
        (b[1] - a[1]).total_seconds() >= 10 for a, b in zip(requested, requested[1:], strict=False)
    )
    assert not News.objects.exists()
    candidate = NewsCandidate.objects.get()
    news = review_candidate(user=moderator, candidate_id=candidate.pk, action="approve")
    assert client.get(f"/api/v1/news/{news.pk}").json()["title"] == candidate.title
    assert client.get("/api/v1/news").json()["count"] == 1
