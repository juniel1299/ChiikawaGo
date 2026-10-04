from datetime import timedelta

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.utils import timezone

from apps.encounters.admin import EffectiveStatusFilter
from apps.encounters.models import Encounter, SpawnRule
from apps.encounters.services import create_encounter

pytestmark = pytest.mark.django_db


def test_spawn_rule_admin_validation_and_immutable_relations(user, spawn_rule):
    user.is_staff = user.is_superuser = True
    user.save()
    request = RequestFactory().get("/admin/")
    request.user = user
    model_admin = admin.site._registry[SpawnRule]
    form = model_admin.get_form(request)(
        data={
            "spot": spawn_rule.spot_id,
            "character_variant": spawn_rule.character_variant_id,
            "weight": 0,
            "is_active": True,
        }
    )
    assert not form.is_valid()
    assert "weight" in form.errors
    update_form = model_admin.get_form(request, spawn_rule)
    assert "spot" not in update_form.base_fields
    assert "character_variant" not in update_form.base_fields
    assert model_admin.has_add_permission(request)
    assert model_admin.has_change_permission(request, spawn_rule)
    assert not model_admin.has_delete_permission(request, spawn_rule)
    assert model_admin.get_actions(request) == {}
    future = timezone.now() + timedelta(days=1)
    form = update_form(
        instance=spawn_rule,
        data={
            "weight": 3,
            "is_active": True,
            "starts_at_0": future.strftime("%Y-%m-%d"),
            "starts_at_1": "12:00:00",
            "ends_at_0": future.strftime("%Y-%m-%d"),
            "ends_at_1": "11:00:00",
        },
    )
    assert not form.is_valid()


def test_encounter_admin_read_only_even_for_superuser(client, user, spawn_rule):
    obj, _ = create_encounter(
        user=user, spot_id=spawn_rule.spot_id, latitude=37.5665, longitude=126.978
    )
    user.is_staff = user.is_superuser = True
    user.save()
    client.force_login(user)
    root = "/admin/encounters/encounter/"
    assert client.get(root).status_code == 200
    assert client.get(f"{root}{obj.id}/change/").status_code == 200
    assert client.post(f"{root}{obj.id}/change/", {"status": "expired"}).status_code == 403
    assert client.get(f"{root}add/").status_code == 403
    assert client.post(f"{root}{obj.id}/delete/", {"post": "yes"}).status_code == 403
    obj.refresh_from_db()
    assert obj.status == "active"


def test_encounter_view_permission_and_effective_filter(client, user, spawn_rule):
    obj, _ = create_encounter(
        user=user, spot_id=spawn_rule.spot_id, latitude=37.5665, longitude=126.978
    )
    user.is_staff = True
    user.save()
    client.force_login(user)
    assert client.get("/admin/encounters/encounter/").status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_encounter"))
    assert client.get("/admin/encounters/encounter/").status_code == 200
    Encounter.objects.filter(pk=obj.pk).update(
        spawned_at=timezone.now() - timedelta(minutes=4),
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    model_admin = admin.site._registry[Encounter]
    request = RequestFactory().get("/admin/")
    for status, expected in [("active", 0), ("expired", 1)]:
        filter_ = EffectiveStatusFilter(
            request, {"effective_status": [status]}, Encounter, model_admin
        )
        assert filter_.queryset(request, Encounter.objects.all()).count() == expected
    obj.refresh_from_db()
    assert model_admin.effective_state(obj) == "expired"
    assert obj.status == "active"
