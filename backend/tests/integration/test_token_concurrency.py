from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, current_thread
from time import monotonic

import pytest
from django.db import close_old_connections, connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import serializers, views
from apps.accounts.tokens import locked_refresh_token

pytestmark = pytest.mark.django_db(transaction=True)
URLS = {"refresh": "/api/v1/auth/token/refresh", "logout": "/api/v1/auth/logout"}


@pytest.mark.parametrize(
    "first,second", [("refresh", "logout"), ("logout", "refresh"), ("refresh", "refresh")]
)
def test_requests_wait_on_same_outstanding_row(monkeypatch, user, first, second):
    assert connection.vendor == "postgresql"
    raw = str(RefreshToken.for_user(user))
    locked, release, second_started = Event(), Event(), Event()
    pids = {}
    first_thread = []

    @contextmanager
    def controlled_lock(raw_token):
        with locked_refresh_token(raw_token) as token:
            if current_thread().ident == first_thread[0]:
                locked.set()
                assert release.wait(8), "First request was not released"
            yield token

    monkeypatch.setattr(serializers, "locked_refresh_token", controlled_lock)
    monkeypatch.setattr(views, "locked_refresh_token", controlled_lock)

    def request(kind, position):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[position] = cursor.fetchone()[0]
            if position == 1:
                first_thread.append(current_thread().ident)
            else:
                second_started.set()
            return APIClient().post(URLS[kind], {"refresh": raw})
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(request, first, 1)
        try:
            assert locked.wait(5)
            loser = pool.submit(request, second, 2)
            assert second_started.wait(5)
            deadline = monotonic() + 4
            while True:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", [pids[2]])
                    blockers = cursor.fetchone()[0]
                if pids[1] in blockers:
                    break
                assert monotonic() < deadline, "Second request never waited on first DB lock"
                release.wait(0.01)
        finally:
            release.set()
        winner, loser = winner.result(timeout=12), loser.result(timeout=12)

    assert winner.status_code == (200 if first == "refresh" else 204)
    assert loser.status_code == (401 if second == "refresh" else 403)
    assert BlacklistedToken.objects.count() == 1
    assert OutstandingToken.objects.count() == (2 if first == "refresh" else 1)
    with pytest.raises(TokenError):
        RefreshToken(raw)
    if first == "refresh":
        successor = RefreshToken(winner.data["refresh"])
        assert OutstandingToken.objects.filter(jti=successor["jti"]).exists()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {winner.data['access']}")
        assert client.get("/api/v1/me").status_code == 200


@pytest.mark.parametrize(
    "kind,method", [("refresh", "blacklist"), ("logout", "blacklist"), ("refresh", "outstand")]
)
def test_failure_rolls_back_all_token_changes(monkeypatch, user, kind, method):
    raw = str(RefreshToken.for_user(user))
    original = getattr(RefreshToken, method)

    def fail_after_write(self):
        original(self)
        raise RuntimeError("Injected failure after token write")

    monkeypatch.setattr(RefreshToken, method, fail_after_write)
    response = APIClient().post(URLS[kind], {"refresh": raw})
    assert response.status_code == 500
    assert OutstandingToken.objects.count() == 1
    assert not BlacklistedToken.objects.exists()
    assert RefreshToken(raw)


@pytest.mark.parametrize("kind,status", [("refresh", 401), ("logout", 403)])
def test_missing_outstanding_token_is_not_recreated(user, kind, status):
    raw = str(RefreshToken.for_user(user))
    OutstandingToken.objects.all().delete()
    assert APIClient().post(URLS[kind], {"refresh": raw}).status_code == status
    assert not OutstandingToken.objects.exists()
    assert not BlacklistedToken.objects.exists()
