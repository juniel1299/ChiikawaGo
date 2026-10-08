import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        "walker@example.com", "Walking-in-the-park-42!", display_name="산책자"
    )


@pytest.fixture
def authenticated(client, user):
    client.force_authenticate(user)
    return client


@pytest.fixture
def spawn_rule(db):
    from django.contrib.gis.geos import Point

    from apps.characters.models import Character, CharacterVariant
    from apps.encounters.models import SpawnRule
    from apps.spatial.models import Spot

    character = Character.objects.create(code="walker", name="Walker")
    variant = CharacterVariant.objects.create(character=character, code="base", name="Base")
    spot = Spot.objects.create(
        code="park", name="Park", location=Point(126.978, 37.5665, srid=4326)
    )
    return SpawnRule.objects.create(spot=spot, character_variant=variant)


@pytest.fixture
def encounter(user, spawn_rule):
    from apps.encounters.services import create_encounter

    return create_encounter(
        user=user, spot_id=spawn_rule.spot_id, latitude=37.5665, longitude=126.978
    )[0]


@pytest.fixture
def community_post(user):
    from apps.community.models import Post

    return Post.objects.create(author=user, category="free", title="산책 이야기", content="본문")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        "community-other@example.com", "Password-42!", display_name="친구"
    )


@pytest.fixture
def moderator(user):
    user.is_staff = user.is_superuser = True
    user.save()
    return user
