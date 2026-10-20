import socket
import ssl
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from apps.news import crawler
from apps.news.models import NewsCandidate
from apps.news.parser import CollectionError
from apps.news.results import CollectionFailure, CollectionResult, TransientCollectionError

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


@pytest.fixture
def execution(news_source):
    from uuid import uuid4

    from apps.batch.models import BatchJob
    from apps.batch.services import request_run

    job = BatchJob.objects.create(
        code="news_collection", name="News", enabled=True, source=news_source
    )
    return request_run(job_id=job.pk, key=uuid4())[0]


def test_task_calls_common_service(execution, monkeypatch):
    from apps.batch.tasks import execute
    from config.celery import app

    collect = Mock(return_value=CollectionResult(created=1))
    monkeypatch.setattr(crawler, "collect", collect)
    assert execute.run(str(execution.pk), 1) == {"created": 1, "skipped": 0, "failed": 0}
    collect.assert_called_once_with(execution.input_snapshot["source_id"])
    assert app.conf.result_backend is None and app.conf.accept_content == ["json"]
    assert execute.acks_late and not execute.reject_on_worker_lost
    assert execute.acks_on_failure_or_timeout


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
def test_permanent_task_error(execution, monkeypatch, code):
    from apps.batch.tasks import BatchTaskError, execute

    monkeypatch.setattr(
        crawler, "collect", lambda _: CollectionResult(errors=[CollectionFailure(code, "detail")])
    )
    retry = Mock()
    monkeypatch.setattr(execute, "retry", retry)
    with pytest.raises(BatchTaskError, match=code):
        execute.run(str(execution.pk), 1)
    retry.assert_not_called()
    execution.refresh_from_db()
    assert execution.status == "failed"


@pytest.mark.parametrize("upper,attempt", [(60, 1), (120, 2)])
def test_retry_delay_and_persistent_attempt(execution, monkeypatch, upper, attempt):
    from celery.exceptions import Retry
    from django.utils import timezone

    from apps.batch import services
    from apps.batch.tasks import execute

    execution.attempt = attempt - 1
    execution.save()
    monkeypatch.setattr(
        crawler,
        "collect",
        lambda _: CollectionResult(errors=[CollectionFailure("network_timeout", "detail", True)]),
    )
    jitter = Mock(return_value=upper / 2)
    retry = Mock(return_value=Retry())
    monkeypatch.setattr(services.random, "uniform", jitter)
    monkeypatch.setattr(execute, "retry", retry)
    with pytest.raises(Retry):
        execute.run(str(execution.pk), attempt)
    jitter.assert_called_once_with(0, upper)
    assert upper / 2 - 1 < retry.call_args.kwargs["countdown"] <= upper / 2
    execution.refresh_from_db()
    assert execution.status == "retry_wait" and execution.next_attempt_at > timezone.now()


@pytest.mark.parametrize("state", ["inactive", "missing", "policy_unchecked"])
def test_source_revalidated_by_worker(execution, news_source, monkeypatch, state):
    from uuid import uuid4

    from apps.batch.tasks import BatchTaskError, execute

    if state == "missing":
        execution.input_snapshot["source_id"] = str(uuid4())
        execution.save()
    else:
        news_source.is_active = False
        if state == "policy_unchecked":
            news_source.policy_checked_at = None
        news_source.save()
    fetch = Mock()
    monkeypatch.setattr(crawler, "fetch", fetch)
    with pytest.raises(BatchTaskError):
        execute.run(str(execution.pk), 1)
    fetch.assert_not_called()


def test_safe_exception_and_time_limit(execution, monkeypatch, caplog):
    from apps.batch.tasks import BatchTaskError, execute

    monkeypatch.setattr(
        crawler, "collect", Mock(side_effect=RuntimeError("password=secret SQLparameter=secret"))
    )
    with pytest.raises(BatchTaskError, match="internal_error"):
        execute.run(str(execution.pk), 1)
    assert (
        "secret" not in caplog.text
        and "stack_trace" in caplog.text
        and str(execution.pk) in caplog.text
    )


def test_soft_limit_and_mixed_errors_never_retry(execution, monkeypatch):
    from billiard.exceptions import SoftTimeLimitExceeded

    from apps.batch import services
    from apps.batch.tasks import BatchTaskError, execute

    retry = Mock()
    monkeypatch.setattr(execute, "retry", retry)
    monkeypatch.setattr(crawler, "collect", Mock(side_effect=SoftTimeLimitExceeded()))
    with pytest.raises(BatchTaskError, match="time_limit"):
        execute.run(str(execution.pk), 1)
    retry.assert_not_called()
    result = CollectionResult(
        errors=[
            CollectionFailure("network_timeout", "detail", True),
            CollectionFailure("invalid_article_metadata", "parse"),
        ]
    )
    monkeypatch.setattr(crawler, "collect", lambda _: result)
    assert not services.run_attempt(execution).retryable


def test_retry_publish_failure_stays_recoverable(execution, monkeypatch):
    from apps.batch.tasks import BatchTaskError, execute

    monkeypatch.setattr(
        crawler,
        "collect",
        lambda _: CollectionResult(errors=[CollectionFailure("network_timeout", "detail", True)]),
    )
    monkeypatch.setattr(execute, "retry", Mock(side_effect=OSError("secret")))
    with pytest.raises(BatchTaskError, match="retry_publish_failed"):
        execute.run(str(execution.pk), 1)
    execution.refresh_from_db()
    assert (
        execution.status == "retry_wait" and execution.dispatch_error_code == "retry_publish_failed"
    )
