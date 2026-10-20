import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from apps.collection.services import create_collection_entry
from apps.spatial.models import Spot
from apps.spatial.selectors import within_interaction_radius

from .models import CaptureResult, Encounter, SpawnRule
from .selectors import eligible_rules


class NoSpawnRule(APIException):
    status_code = 409
    default_code = "conflict"

    def __init__(self):
        super().__init__({"detail": "출현 가능한 캐릭터가 없습니다.", "reason": "no_spawn_rule"})


def choose_rule(rules):
    ticket = secrets.randbelow(sum(rule.weight for rule in rules))
    for rule in rules:
        if ticket < rule.weight:
            return rule
        ticket -= rule.weight
    raise AssertionError("Weighted selection exhausted candidates")


@transaction.atomic
def create_encounter(*, user, spot_id, latitude, longitude):
    # All creation paths use Spot -> Encounter -> SpawnRule (ordered by UUID).
    # NO KEY UPDATE allows FK references without relaxing competing update locks.
    try:
        spot = Spot.objects.select_for_update(no_key=True).get(pk=spot_id)
    except Spot.DoesNotExist as exc:
        raise NotFound("장소를 찾을 수 없습니다.") from exc
    if not spot.is_active:
        raise NotFound("장소를 찾을 수 없습니다.")
    if not within_interaction_radius(spot=spot, latitude=latitude, longitude=longitude):
        raise PermissionDenied({"detail": "장소의 허용 거리 밖입니다.", "reason": "out_of_range"})
    existing = (
        Encounter.objects.select_for_update(no_key=True)
        .filter(user=user, spot=spot, status=Encounter.Status.ACTIVE)
        .first()
    )
    if existing and existing.effective_status() == Encounter.Status.ACTIVE:
        return existing, False

    rules = list(
        SpawnRule.objects.select_for_update(of=("self",), no_key=True)
        .filter(spot=spot)
        .order_by("id")
    )
    # Sample time after every potentially blocking row lock, not at request start.
    now = timezone.now()
    candidates = eligible_rules(rules, at=now)
    if not candidates:
        raise NoSpawnRule()
    selected = choose_rule(candidates)
    if existing:
        existing.status = Encounter.Status.EXPIRED
        existing.save(update_fields=["status"])
    encounter = Encounter.objects.create(
        user=user,
        spot=spot,
        character_variant_id=selected.character_variant_id,
        spawned_at=now,
        expires_at=now + timedelta(seconds=settings.ENCOUNTER_TTL_SECONDS),
    )
    return encounter, True


class EncounterExpired(APIException):
    status_code = 409
    default_code = "conflict"

    def __init__(self):
        super().__init__({"detail": "만료된 Encounter입니다.", "reason": "encounter_expired"})


class CaptureConsistencyError(RuntimeError):
    pass


@transaction.atomic
def capture_encounter(*, user, encounter_id):
    # Never acquire a Spot lock after this lock: creation uses Spot -> Encounter.
    try:
        encounter = Encounter.objects.select_for_update(of=("self",), no_key=True).get(
            pk=encounter_id, user=user
        )
    except Encounter.DoesNotExist as exc:
        raise NotFound("Encounter를 찾을 수 없습니다.") from exc
    result = (
        CaptureResult.objects.select_related("collection_entry").filter(encounter=encounter).first()
    )
    if encounter.status == Encounter.Status.CAPTURED:
        entry = getattr(result, "collection_entry", None) if result else None
        if (
            entry is None
            or entry.user_id != encounter.user_id
            or entry.character_variant_id != encounter.character_variant_id
        ):
            raise CaptureConsistencyError("Captured encounter has inconsistent acquisition records")
        result.encounter = encounter
        return result
    if result is not None:
        raise CaptureConsistencyError("Uncaptured encounter already has a capture result")
    now = timezone.now()
    if encounter.effective_status(at=now) != Encounter.Status.ACTIVE:
        raise EncounterExpired()
    result = CaptureResult.objects.create(encounter=encounter, captured_at=now)
    create_collection_entry(capture_result=result)
    encounter.status = Encounter.Status.CAPTURED
    encounter.save(update_fields=["status"])
    return result
