import json
import socket
import ssl
from io import StringIO
from unittest.mock import Mock
from urllib.error import URLError
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction

from apps.news import crawler, enqueue, tasks
from apps.news.models import NewsCandidate
from apps.news.parser import CollectionError
from apps.news.results import CollectionFailure, CollectionResult, TransientCollectionError
from config.celery import app

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "error,transient,code",
    [
        (TimeoutError("private"), True, "network_timeout"),
        (URLError(TimeoutError("private")), True, "network_timeout"),
        (URLError(ConnectionResetError("private")), True, "network_connection"),
        (URLError(ConnectionRefusedError("private")), True, "network_connection"),
        (URLError(socket.gaierror(socket.EAI_AGAIN, "private")), True, "network_dns_temporary"),
        (URLError(socket.gaierror(socket.EAI_NONAME, "private")), False, "fetch_failed"),
        (URLError(ssl.SSLCertVerificationError("private")), False, "fetch_failed"),
        (URLError("private"), False, "fetch_failed"),
        (UnicodeError("private"), False, "fetch_failed"),
    ],
)
def test_transport_failure_classification(news_source, monkeypatch, error, transient, code):
    opener = Mock()
    opener.open.side_effect = error
    monkeypatch.setattr(crawler, "build_opener", lambda *args: opener)
    with pytest.raises(CollectionError) as caught:
        crawler.fetch(news_source.pk, "https://www.dreamnews.jp/press/0000000001")
    assert str(caught.value) == code
    assert isinstance(caught.value, TransientCollectionError) is transient
    assert opener.open.call_count == 1


def test_mixed_result_never_retries():
    result = CollectionResult(errors=[CollectionFailure("network_timeout", "detail", True)])
    assert result.retryable
    result.errors.append(CollectionFailure("robots_denied", "robots"))
    assert not result.retryable


def test_task_calls_common_service(news_source, monkeypatch):
    collect = Mock(return_value=CollectionResult(created=1))
    monkeypatch.setattr(crawler, "collect", collect)
    assert tasks.collect_news_source.run(str(news_source.pk)) == {
        "created": 1,
        "skipped": 0,
        "failed": 0,
    }
    collect.assert_called_once_with(str(news_source.pk))
    assert app.conf.result_backend is None and app.conf.accept_content == ["json"]
    assert app.conf.task_serializer == "json"
    assert tasks.collect_news_source.acks_late
    assert not tasks.collect_news_source.reject_on_worker_lost
    assert tasks.collect_news_source.acks_on_failure_or_timeout


@pytest.mark.parametrize("attempt,upper", [(0, 60), (1, 120)])
def test_limited_retry_jitter(news_source, monkeypatch, attempt, upper):
    monkeypatch.setattr(
        crawler,
        "collect",
        lambda _: CollectionResult(errors=[CollectionFailure("network_timeout", "robots", True)]),
    )
    jitter = Mock(return_value=upper / 2)
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks.random, "uniform", jitter)
    monkeypatch.setattr(tasks.collect_news_source, "retry", retry)
    tasks.collect_news_source.push_request(id="test", retries=attempt)
    try:
        with pytest.raises(Retry):
            tasks.collect_news_source.run(str(news_source.pk))
    finally:
        tasks.collect_news_source.pop_request()
    jitter.assert_called_once_with(0, upper)
    assert retry.call_args.kwargs["countdown"] == upper / 2


@pytest.mark.parametrize(
    "code",
    [
        "http_403",
        "http_429",
        "http_500",
        "robots_denied",
        "access_challenge",
        "invalid_article_metadata",
        "identity_conflict",
    ],
)
def test_nonretryable_task_failure(news_source, monkeypatch, code):
    monkeypatch.setattr(
        crawler, "collect", lambda _: CollectionResult(errors=[CollectionFailure(code, "detail")])
    )
    retry = Mock()
    monkeypatch.setattr(tasks.collect_news_source, "retry", retry)
    with pytest.raises(tasks.CollectionTaskError, match="collection_failed"):
        tasks.collect_news_source.run(str(news_source.pk))
    retry.assert_not_called()


def test_retry_exhaustion(news_source, monkeypatch):
    monkeypatch.setattr(
        crawler,
        "collect",
        lambda _: CollectionResult(errors=[CollectionFailure("network_timeout", "detail", True)]),
    )
    tasks.collect_news_source.push_request(id="test", retries=2)
    try:
        with pytest.raises(tasks.CollectionTaskError, match="retry_exhausted"):
            tasks.collect_news_source.run(str(news_source.pk))
    finally:
        tasks.collect_news_source.pop_request()


@pytest.mark.parametrize("state", ["missing", "inactive", "invalid", "policy_unchecked"])
def test_invalid_source_never_fetches(news_source, monkeypatch, state):
    source_id = (
        str(uuid4())
        if state == "missing"
        else "not-a-uuid"
        if state == "invalid"
        else str(news_source.pk)
    )
    if state == "inactive":
        news_source.is_active = False
        news_source.save()
    if state == "policy_unchecked":
        news_source.is_active = False
        news_source.policy_checked_at = None
        news_source.save()
    fetch = Mock()
    monkeypatch.setattr(crawler, "fetch", fetch)
    with pytest.raises(tasks.CollectionTaskError):
        tasks.collect_news_source.run(source_id)
    fetch.assert_not_called()


def test_safe_task_failure_logs(news_source, monkeypatch, caplog):
    def fail(_):
        raise RuntimeError("password=secret rawhtml SQLparameter=secret")

    monkeypatch.setattr(crawler, "collect", fail)
    tasks.collect_news_source.push_request(id="safe-task-id", retries=0)
    try:
        with pytest.raises(tasks.CollectionTaskError, match="internal_error"):
            tasks.collect_news_source.run(str(news_source.pk))
    finally:
        tasks.collect_news_source.pop_request()
    output = caplog.text
    assert "secret" not in output
    assert "safe-task-id" in output and "stack_trace" in output


def test_commit_before_publish(news_source, monkeypatch, django_capture_on_commit_callbacks):
    publish = Mock()
    monkeypatch.setattr(tasks.collect_news_source, "apply_async", publish)
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            task_id = enqueue.enqueue_collection(news_source.pk)
            publish.assert_not_called()
    publish.assert_called_once_with(args=[str(news_source.pk)], task_id=task_id, retry=False)
    json.dumps(publish.call_args.kwargs["args"])


def test_rollback_discards_publish(news_source, monkeypatch, django_capture_on_commit_callbacks):
    publish = Mock()
    monkeypatch.setattr(tasks.collect_news_source, "apply_async", publish)
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            enqueue.enqueue_collection(news_source.pk)
            raise RuntimeError("rollback")
    publish.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_enqueue_command_receipt_and_failure(news_source, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(tasks.collect_news_source, "apply_async", publish)
    output = StringIO()
    call_command("enqueue_news_collection", source=news_source.code, stdout=output)
    assert "published task_id=" in output.getvalue()
    publish.side_effect = OSError("broker secret")
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("enqueue_news_collection", source=news_source.code, stdout=output)
    assert not output.getvalue()


def test_retry_publish_failure_is_sanitized(news_source, monkeypatch):
    monkeypatch.setattr(
        crawler,
        "collect",
        lambda _: CollectionResult(errors=[CollectionFailure("network_timeout", "detail", True)]),
    )
    monkeypatch.setattr(tasks.collect_news_source, "retry", Mock(side_effect=OSError("secret")))
    with pytest.raises(tasks.CollectionTaskError, match="retry_publish_failed"):
        tasks.collect_news_source.run(str(news_source.pk))


def test_partial_transient_failure_then_reexecution(news_source, monkeypatch):
    from tests.integration.test_news import FIXTURES, URL

    listing = (FIXTURES / "list.html").read_text()
    listing += listing.replace("0000000001", "0000000004")
    detail = (FIXTURES / "detail.html").read_text()

    def fetch(source_id, url, **kwargs):
        if url == crawler.ROBOTS_URL:
            return "User-agent: *\nDisallow:\n"
        if url == crawler.DREAMNEWS_LIST:
            return listing
        if url == URL:
            return detail
        raise TransientCollectionError("network_timeout")

    monkeypatch.setattr(crawler, "fetch", fetch)
    first = crawler.collect(news_source.pk)
    second = crawler.collect(news_source.pk)
    assert first.retryable and first.created == 1
    assert second.skipped == 1 and second.retryable
    assert NewsCandidate.objects.count() == 1


def test_soft_limit_never_retries(news_source, monkeypatch):
    from billiard.exceptions import SoftTimeLimitExceeded

    monkeypatch.setattr(crawler, "collect", Mock(side_effect=SoftTimeLimitExceeded()))
    retry = Mock()
    monkeypatch.setattr(tasks.collect_news_source, "retry", retry)
    with pytest.raises(tasks.CollectionTaskError, match="time_limit"):
        tasks.collect_news_source.run(str(news_source.pk))
    retry.assert_not_called()


def test_mixed_task_failure_never_retries(news_source, monkeypatch):
    result = CollectionResult(
        errors=[
            CollectionFailure("network_timeout", "detail_fetch", True),
            CollectionFailure("invalid_article_metadata", "detail_parse"),
        ]
    )
    monkeypatch.setattr(crawler, "collect", lambda _: result)
    retry = Mock()
    monkeypatch.setattr(tasks.collect_news_source, "retry", retry)
    with pytest.raises(tasks.CollectionTaskError, match="collection_failed"):
        tasks.collect_news_source.run(str(news_source.pk))
    retry.assert_not_called()
