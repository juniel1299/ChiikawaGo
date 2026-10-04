from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.collection.models import CollectionEntry
from apps.encounters import services
from apps.encounters.models import CaptureResult, Encounter
from tests.integration.test_encounter_concurrency import post, run_overlapping

pytestmark = pytest.mark.django_db(transaction=True)


def capture(user, encounter):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(f"/api/v1/encounters/{encounter.id}/capture")


def hold_at_result_save(monkeypatch, locked, release, fail=False):
    original = CaptureResult.save

    def controlled(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if not locked.is_set():
            locked.set()
            assert release.wait(10)
            if fail:
                raise RuntimeError("Injected first capture failure")

    monkeypatch.setattr(CaptureResult, "save", controlled)


def test_simultaneous_capture_same_result(user, encounter, monkeypatch):
    locked, release = Event(), Event()
    hold_at_result_save(monkeypatch, locked, release)
    a, b = run_overlapping(
        lambda: capture(user, encounter), lambda: capture(user, encounter), locked, release
    )
    assert a.status_code == b.status_code == 200
    assert a.data == b.data
    assert CaptureResult.objects.count() == CollectionEntry.objects.count() == 1
    encounter.refresh_from_db()
    assert encounter.status == "captured"


@pytest.mark.parametrize("expire", [False, True])
def test_first_failure_allows_retry_or_expiry(user, encounter, monkeypatch, expire):
    locked, release = Event(), Event()
    hold_at_result_save(monkeypatch, locked, release, fail=True)
    clock = [timezone.now()]
    monkeypatch.setattr(services.timezone, "now", lambda: clock[0])
    a, b = run_overlapping(
        lambda: capture(user, encounter),
        lambda: capture(user, encounter),
        locked,
        release,
        before_release=(lambda: clock.__setitem__(0, encounter.expires_at)) if expire else None,
    )
    assert a.status_code == 500
    assert b.status_code == (409 if expire else 200)
    assert CaptureResult.objects.count() == CollectionEntry.objects.count() == (0 if expire else 1)
    encounter.refresh_from_db()
    assert encounter.status == ("active" if expire else "captured")


def test_lock_wait_crossing_expiry(user, encounter, monkeypatch):
    locked, release = Event(), Event()
    clock = [timezone.now()]
    monkeypatch.setattr(services.timezone, "now", lambda: clock[0])

    def hold():
        with transaction.atomic():
            Encounter.objects.select_for_update(no_key=True).get(pk=encounter.pk)
            locked.set()
            assert release.wait(10)

    _, result = run_overlapping(
        hold,
        lambda: capture(user, encounter),
        locked,
        release,
        before_release=lambda: clock.__setitem__(0, encounter.expires_at),
    )
    assert result.status_code == 409
    assert not CollectionEntry.objects.exists()


def test_capture_then_encounter_creation(user, encounter, spawn_rule, monkeypatch):
    locked, release = Event(), Event()
    hold_at_result_save(monkeypatch, locked, release)
    a, b = run_overlapping(
        lambda: capture(user, encounter), lambda: post(user, spawn_rule), locked, release
    )
    assert a.status_code == 200
    assert b.status_code == 201
    assert b.data["id"] != str(encounter.id)
    assert Encounter.objects.filter(status="active").count() == 1
    assert CollectionEntry.objects.count() == 1


@pytest.mark.parametrize("expired", [False, True])
def test_creation_then_capture(user, encounter, spawn_rule, monkeypatch, expired):
    locked, release = Event(), Event()
    if expired:
        Encounter.objects.filter(pk=encounter.pk).update(
            spawned_at=timezone.now() - timedelta(minutes=4),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        original = Encounter.save

        def pause_save(self, *args, **kwargs):
            original(self, *args, **kwargs)
            if self.pk == encounter.pk and self.status == "expired":
                locked.set()
                assert release.wait(10)

        monkeypatch.setattr(Encounter, "save", pause_save)
    else:
        original = Encounter.effective_status

        def pause_status(self, at=None):
            if not locked.is_set():
                locked.set()
                assert release.wait(10)
            return original(self, at=at)

        monkeypatch.setattr(Encounter, "effective_status", pause_status)
    a, b = run_overlapping(
        lambda: post(user, spawn_rule), lambda: capture(user, encounter), locked, release
    )
    assert a.status_code == (201 if expired else 200)
    assert b.status_code == (409 if expired else 200)
    assert CollectionEntry.objects.count() == (0 if expired else 1)


def test_different_encounter_same_spot_can_capture_independently(user, encounter, spawn_rule):
    other = User.objects.create_user("parallel@example.com", "password")
    other_encounter, _ = services.create_encounter(
        user=other, spot_id=spawn_rule.spot_id, latitude=37.5665, longitude=126.978
    )

    def run():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '3s'")
            return capture(other, other_encounter)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Encounter.objects.select_for_update(no_key=True).get(pk=encounter.pk)
            assert pool.submit(run).result(timeout=5).status_code == 200
    assert CollectionEntry.objects.count() == 1
