from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.encounters.models import SpawnRule
from apps.encounters.selectors import eligible_rules
from apps.encounters.services import choose_rule

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("weight", [0, -1])
def test_invalid_weights_rejected_by_model_and_db(spawn_rule, weight):
    spawn_rule.weight = weight
    with pytest.raises(ValidationError):
        spawn_rule.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        SpawnRule.objects.filter(pk=spawn_rule.pk).update(weight=weight)


@pytest.mark.parametrize("delta", [0, -1])
def test_period_constraint(spawn_rule, delta):
    spawn_rule.starts_at = timezone.now()
    spawn_rule.ends_at = spawn_rule.starts_at + timedelta(seconds=delta)
    with pytest.raises(ValidationError):
        spawn_rule.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        spawn_rule.save()


def test_duplicate_rule_constraint(spawn_rule):
    with pytest.raises(IntegrityError), transaction.atomic():
        SpawnRule.objects.create(
            spot=spawn_rule.spot, character_variant=spawn_rule.character_variant
        )


@pytest.mark.parametrize(
    "start,end,active,expected",
    [
        (None, None, True, True),
        (0, 1, True, True),
        (1, None, True, False),
        (None, 0, True, False),
        (None, -1, True, False),
        (-1, None, True, True),
        (None, 1, True, True),
        (None, None, False, False),
    ],
)
def test_rule_period_boundaries(spawn_rule, start, end, active, expected):
    now = timezone.now()
    spawn_rule.starts_at = None if start is None else now + timedelta(seconds=start)
    spawn_rule.ends_at = None if end is None else now + timedelta(seconds=end)
    spawn_rule.is_active = active
    assert bool(eligible_rules([spawn_rule], at=now)) is expected


@pytest.mark.parametrize("target", ["variant", "character"])
def test_inactive_catalog_excluded(spawn_rule, target):
    obj = spawn_rule.character_variant
    if target == "character":
        obj = obj.character
    obj.is_active = False
    obj.save()
    assert eligible_rules([spawn_rule], at=timezone.now()) == []


@pytest.mark.parametrize("ticket,index", [(0, 0), (1, 0), (2, 1), (4, 1), (5, 2), (11, 2)])
def test_weighted_interval_boundaries(monkeypatch, ticket, index):
    rules = [SimpleNamespace(weight=n) for n in [2, 3, 7]]

    def randbelow(total):
        assert total == 12
        return ticket

    monkeypatch.setattr("apps.encounters.services.secrets.randbelow", randbelow)
    assert choose_rule(rules) is rules[index]


def test_single_weighted_candidate():
    rule = SimpleNamespace(weight=7)
    assert choose_rule([rule]) is rule
