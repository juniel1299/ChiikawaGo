"""Test-only subprocess bootstrap. Never imported by production autodiscovery."""

import json
import os
import time
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import django

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
django.setup()

from celery import current_task  # noqa: E402
from django.conf import settings  # noqa: E402
from kombu import Queue  # noqa: E402

from apps.batch import services, tasks  # noqa: E402
from apps.news import crawler  # noqa: E402
from apps.news.models import NewsCandidate  # noqa: E402
from config.celery import app  # noqa: E402

control = Path(os.environ["BROKER_TEST_CONTROL"])
queue = os.environ["BROKER_TEST_QUEUE"]
mode = os.environ["BROKER_TEST_MODE"]
assert settings.DATABASES["default"]["NAME"].startswith("test_")
assert queue.startswith("test.news.")
fixtures = Path(__file__).resolve().parents[1] / "fixtures/news"
listing = (fixtures / "list.html").read_text()
detail = (fixtures / "detail.html").read_text()
url = "https://www.dreamnews.jp/press/0000000001"
# Keep production retry limits; remove real-time delays only inside this test process.
services.random.uniform = lambda a, b: 0
crawler.INTERVAL_SECONDS = 0


class Response(BytesIO):
    status = 200

    def __init__(self, body, content_type):
        super().__init__(body.encode())
        self.headers = Message()
        self.headers["Content-Type"] = content_type


class FixtureTransport:
    def open(self, request, timeout):
        address = request.full_url
        with (control / "requests").open("a") as log:
            log.write(json.dumps({"url": address, "retry": current_task.request.retries}) + "\n")
        if mode in ("transient", "retry_publish_lost") and current_task.request.retries == 0:
            raise TimeoutError("test timeout")
        if mode == "exhaust":
            raise TimeoutError("test timeout")
        if mode == "forbidden":
            raise HTTPError(address, 403, "private body must not escape", Message(), None)
        if address == crawler.ROBOTS_URL:
            return Response("User-agent: *\nDisallow:\n", "text/plain")
        if address == crawler.DREAMNEWS_LIST:
            body = listing
            if mode in ("pause", "kill_child"):
                body += listing.replace("0000000001", "0000000004")
            return Response(body, "text/html")
        if address == url:
            return Response(detail, "text/html")
        if address == url[:-1] + "4" and mode in ("pause", "kill_child"):
            if not (control / "once").exists():
                (control / "once").write_text(str(os.getpid()))
                if mode == "kill_child":
                    os._exit(17)
                (control / "paused").write_text("ready")
                deadline = time.monotonic() + 30
                while not (control / "release").exists():
                    if time.monotonic() > deadline:
                        raise RuntimeError("test barrier timed out")
                    time.sleep(0.02)
            return Response(detail.replace("0000000001", "0000000004"), "text/html")
        raise AssertionError("unexpected outbound request in broker test")


crawler.build_opener = lambda *args: FixtureTransport()
if mode == "rollback":
    original_save = NewsCandidate.save

    def fail_once(self, *args, **kwargs):
        original_save(self, *args, **kwargs)
        if not (control / "once").exists():
            (control / "once").write_text("failed")
            raise RuntimeError("injected save failure")

    NewsCandidate.save = fail_once

if mode == "retry_publish_lost":
    original_retry = tasks.execute.retry

    def lose_retry(*args, **kwargs):
        if not (control / "once").exists():
            (control / "once").write_text("lost")
            raise OSError("injected broker loss")
        return original_retry(*args, **kwargs)

    tasks.execute.retry = lose_retry

if mode == "completion_lost":

    def fail_completion(*args, **kwargs):
        (control / "completion_lost").write_text("ready")
        raise RuntimeError("injected final record failure")

    services.finish_attempt = fail_completion

app.conf.update(
    CELERY_TASK_QUEUES=[Queue(queue, exchange=queue, routing_key=queue, durable=True)],
    CELERY_TASK_DEFAULT_QUEUE=queue,
    CELERY_TASK_DEFAULT_EXCHANGE=queue,
    CELERY_TASK_DEFAULT_ROUTING_KEY=queue,
    CELERY_TASK_ROUTES={"batch.execute": {"queue": queue}},
)
app.worker_main(
    [
        "worker",
        "--pool=prefork",
        "--concurrency=1",
        "--loglevel=INFO",
        "--queues=" + queue,
        "--hostname=test@" + queue,
        "--without-gossip",
        "--without-mingle",
    ]
)
