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
