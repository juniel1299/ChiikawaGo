from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.cleanup import clean_expired_tokens

pytestmark = pytest.mark.django_db(transaction=True)


def test_cleanup_expiry_cascade_and_locked_skip(user):
    token = RefreshToken.for_user(user)
    token.blacklist()
    row = OutstandingToken.objects.get(jti=token["jti"])
    OutstandingToken.objects.filter(pk=row.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    RefreshToken.for_user(user)

    def clean():
        close_old_connections()
        try:
            return clean_expired_tokens(batch_size=1)
        finally:
            connection.close()

    with transaction.atomic(), ThreadPoolExecutor(max_workers=1) as pool:
        OutstandingToken.objects.select_for_update().get(pk=row.pk)
        assert pool.submit(clean).result(timeout=5)["outstanding_deleted"] == 0
    assert clean_expired_tokens(batch_size=1) == {
        "outstanding_deleted": 1,
        "blacklisted_deleted": 1,
    }
    assert OutstandingToken.objects.count() == 1 and not BlacklistedToken.objects.exists()


def test_cleanup_chunk_failure_rolls_back(user, monkeypatch):
    token = RefreshToken.for_user(user)
    token.blacklist()
    OutstandingToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    from django.db.models.query import QuerySet

    original = QuerySet.delete

    def fail(self):
        value = original(self)
        if self.model is OutstandingToken:
            raise RuntimeError("injected")
        return value

    monkeypatch.setattr(QuerySet, "delete", fail)
    with pytest.raises(RuntimeError):
        clean_expired_tokens()
    assert OutstandingToken.objects.count() == BlacklistedToken.objects.count() == 1


@pytest.mark.parametrize("action", ["refresh", "logout"])
def test_auth_holds_outstanding_lock_while_cleanup_skips(user, monkeypatch, action):
    from contextlib import contextmanager
    from threading import Event

    from rest_framework.test import APIClient

    from apps.accounts import serializers, views
    from apps.accounts.tokens import locked_refresh_token

    token = RefreshToken.for_user(user)
    raw = str(token)
    row = OutstandingToken.objects.get(jti=token["jti"])
    locked, release = Event(), Event()

    @contextmanager
    def pause(raw_token):
        with locked_refresh_token(raw_token) as parsed:
            locked.set()
            assert release.wait(10)
            yield parsed

    monkeypatch.setattr(
        serializers if action == "refresh" else views, "locked_refresh_token", pause
    )

    def auth():
        close_old_connections()
        try:
            url = "/api/v1/auth/token/refresh" if action == "refresh" else "/api/v1/auth/logout"
            return APIClient().post(url, {"refresh": raw}, format="json")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(auth)
        try:
            assert locked.wait(5)
            # A cleanup cutoff can pass expiry while an already-started auth transaction holds it.
            assert clean_expired_tokens(cutoff=row.expires_at)["outstanding_deleted"] == 0
        finally:
            release.set()
        assert future.result(timeout=10).status_code == (200 if action == "refresh" else 204)
    assert BlacklistedToken.objects.filter(token=row).exists()
