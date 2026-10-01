import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.characters.models import Character, CharacterVariant

pytestmark = pytest.mark.django_db


def test_public_catalog_hides_inactive_records(client):
    character = Character.objects.create(code="chii", name="치이")
    hidden = Character.objects.create(code="hidden", name="비공개", is_active=False)
    variant = CharacterVariant.objects.create(character=character, code="default", name="기본")
    CharacterVariant.objects.create(
        character=character, code="hidden", name="비공개", is_active=False
    )
    response = client.get("/api/v1/characters")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert client.get(f"/api/v1/characters/{hidden.pk}").status_code == 404
    assert client.get(f"/api/v1/characters/{hidden.pk}/variants").status_code == 404
    variants = client.get(f"/api/v1/characters/{character.pk}/variants").data
    assert [row["id"] for row in variants["results"]] == [str(variant.pk)]
    assert client.post("/api/v1/characters", {}).status_code == 405


def test_variant_constraints_and_reference_protection():
    character = Character.objects.create(code="chii", name="치이")
    CharacterVariant.objects.create(character=character, code="default", name="기본")
    with pytest.raises(IntegrityError), transaction.atomic():
        CharacterVariant.objects.create(character=character, code="default", name="중복")
    with pytest.raises(IntegrityError), transaction.atomic():
        CharacterVariant.objects.create(
            character=character, code="bad", name="오류", rarity="legendary"
        )
    with pytest.raises(ProtectedError):
        character.delete()
