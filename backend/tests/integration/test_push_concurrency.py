from threading import Event
from unittest.mock import patch

import pytest
from django.db import transaction

from apps.notifications import delivery, services
from apps.notifications.models import PushDelivery, PushDevice
from apps.notifications.provider import Outcome
from tests.integration.test_encounter_concurrency import run_overlapping
from tests.integration.test_notifications import device, message, payload

pytestmark = pytest.mark.django_db(transaction=True)


def test_binding_compare_and_swap_waits_for_real_lock(user, other_user):
    d = device(user)
    locked, release = Event(), Event()

    def first():
        with transaction.atomic():
            PushDevice.objects.select_for_update().get(pk=d.pk)
            locked.set()
            assert release.wait(10)
            return services.register(
                user=other_user, installation_id=d.installation_id, **payload(1)
            )[0].binding_version

    def second():
        try:
            services.unregister(
                user=user,
                installation_id=d.installation_id,
                installation_secret=payload()["installation_secret"],
                binding_version=1,
            )
        except services.Conflict:
            return "conflict"

    assert run_overlapping(first, second, locked, release) == (2, "conflict")
    d.refresh_from_db()
    assert d.user == other_user and d.enabled


def test_duplicate_claim_real_lock(user, moderator):
    d = device(user)
    with patch("apps.notifications.services.enqueue_safely"):
        row = message(moderator, user).deliveries.get()
    locked, release = Event(), Event()

    def first():
        # Hold the service's first lock to prove overlapping DB transactions.
        with transaction.atomic():
            PushDevice.objects.select_for_update().get(pk=d.pk)
            locked.set()
            assert release.wait(10)
            delivery.execute(row.pk, 1)

    with patch(
        "apps.notifications.provider.send", return_value=Outcome(message_id="synthetic")
    ) as send:
        run_overlapping(first, lambda: delivery.execute(row.pk, 1), locked, release)
        assert send.call_count == 1
    assert PushDelivery.objects.get(pk=row.pk).status == "SENT"


def test_bootstrap_concurrent_creation_is_not_an_upsert(user, other_user):
    import uuid

    installation = uuid.uuid4()
    locked, release = Event(), Event()

    def first():
        with transaction.atomic():
            result, created = services.register(
                user=user, installation_id=installation, **payload()
            )
            assert created and result.binding_version == 1
            locked.set()
            assert release.wait(10)
            return "created"

    def second():
        try:
            services.register(user=other_user, installation_id=installation, **payload())
        except services.Conflict:
            return "conflict"

    assert run_overlapping(first, second, locked, release) == ("created", "conflict")
    row = PushDevice.objects.get(installation_id=installation)
    assert row.user_id == user.pk and row.binding_version == 1
