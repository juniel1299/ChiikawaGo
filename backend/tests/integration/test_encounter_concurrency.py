from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.encounters import services
from apps.encounters.models import Encounter, SpawnRule
from apps.spatial.models import Spot

pytestmark = pytest.mark.django_db(transaction=True)
ORIGIN = {"latitude": 37.5665, "longitude": 126.978}


def post(user, rule):
    client = APIClient()
    client.force_authenticate(user)
    return client.post("/api/v1/encounters", {"spot_id": str(rule.spot_id), **ORIGIN})


def run_overlapping(first, second, locked, release, before_release=None):
    """Prove that the second PostgreSQL connection waits on the first, then release it."""
    assert connection.vendor == "postgresql"
    pids = {}
    started = Event()

    def run(fn, position):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[position] = cursor.fetchone()[0]
            if position == 2:
                started.set()
            return fn()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, first, 1)
        try:
            assert locked.wait(5)
            b = pool.submit(run, second, 2)
            assert started.wait(5)
            deadline = monotonic() + 5
            while True:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", [pids[2]])
                    blockers = cursor.fetchone()[0]
                if pids[1] in blockers:
                    break
                assert monotonic() < deadline, "Expected actual PostgreSQL lock wait"
                release.wait(0.01)
            if before_release:
                before_release()
        finally:
            release.set()
        return a.result(timeout=15), b.result(timeout=15)


@pytest.mark.parametrize("expired,different_user", [(False, False), (True, False), (False, True)])
def test_create_race(monkeypatch, user, spawn_rule, expired, different_user):
    from apps.accounts.models import User

    old = None
    if expired:
        old = Encounter.objects.create(
            user=user,
            spot=spawn_rule.spot,
            character_variant=spawn_rule.character_variant,
            spawned_at=timezone.now() - timedelta(minutes=4),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
    other = User.objects.create_user("second@example.com", "password") if different_user else user
    locked, release = Event(), Event()
    original = services.within_interaction_radius

    def pause_with_spot_lock(**kwargs):
        if not locked.is_set():
            locked.set()
            assert release.wait(10)
        return original(**kwargs)

    monkeypatch.setattr(services, "within_interaction_radius", pause_with_spot_lock)
    a, b = run_overlapping(
        lambda: post(user, spawn_rule), lambda: post(other, spawn_rule), locked, release
    )
    assert a.status_code == 201
    assert b.status_code == (201 if different_user else 200)
    assert (a.data["id"] != b.data["id"]) is different_user
    assert Encounter.objects.filter(status="active").count() == (2 if different_user else 1)
    if not different_user:
        assert a.data == b.data
    if old:
        old.refresh_from_db()
        assert old.status == "expired"


@pytest.mark.parametrize("update_first", [False, True])
def test_rule_deactivation_race(monkeypatch, user, spawn_rule, update_first):
    locked, release = Event(), Event()
    if not update_first:
        original = services.eligible_rules

        def pause_with_rule_lock(*args, **kwargs):
            locked.set()
            assert release.wait(10)
            return original(*args, **kwargs)

        monkeypatch.setattr(services, "eligible_rules", pause_with_rule_lock)

    def deactivate():
        with transaction.atomic():
            SpawnRule.objects.filter(pk=spawn_rule.pk).update(is_active=False)
            if update_first:
                locked.set()
                assert release.wait(10)

    def create():
        return post(user, spawn_rule)

    first, second = (deactivate, create) if update_first else (create, deactivate)
    a, b = run_overlapping(first, second, locked, release)
    result = b if update_first else a
    assert result.status_code == (409 if update_first else 201)
    assert Encounter.objects.count() == (0 if update_first else 1)
    spawn_rule.refresh_from_db()
    assert not spawn_rule.is_active


def test_time_is_sampled_after_rule_lock_wait(monkeypatch, user, spawn_rule):
    locked, release = Event(), Event()
    now = timezone.now()
    end = now + timedelta(seconds=10)
    SpawnRule.objects.filter(pk=spawn_rule.pk).update(ends_at=end)
    clock = [now]
    monkeypatch.setattr(services.timezone, "now", lambda: clock[0])

    def hold_rule():
        with transaction.atomic():
            SpawnRule.objects.select_for_update(no_key=True).get(pk=spawn_rule.pk)
            locked.set()
            assert release.wait(10)

    _, result = run_overlapping(
        hold_rule,
        lambda: post(user, spawn_rule),
        locked,
        release,
        before_release=lambda: clock.__setitem__(0, end),
    )
    assert result.status_code == 409
    assert not Encounter.objects.exists()


def test_different_spot_does_not_wait(user, spawn_rule):
    other_spot = Spot.objects.create(code="other", name="Other", location=spawn_rule.spot.location)
    other_rule = SpawnRule.objects.create(
        spot=other_spot, character_variant=spawn_rule.character_variant
    )

    def create_elsewhere():
        close_old_connections()
        try:
            return post(user, other_rule)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Spot.objects.select_for_update(no_key=True).get(pk=spawn_rule.spot_id)
            response = pool.submit(create_elsewhere).result(timeout=5)
            assert response.status_code == 201
