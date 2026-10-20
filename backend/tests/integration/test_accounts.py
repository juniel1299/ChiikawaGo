from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import User

pytestmark = pytest.mark.django_db
PASSWORD = "Walking-in-the-park-42!"


def test_register_normalizes_email_and_hashes_password(client):
    response = client.post(
        "/api/v1/auth/register",
        {
            "email": "Walker@EXAMPLE.com",
            "password": PASSWORD,
            "display_name": "산책자",
        },
    )
    assert response.status_code == 201
    assert response.data["email"] == "walker@example.com"
    assert "password" not in response.data
    assert User.objects.get().check_password(PASSWORD)


def test_duplicate_email_is_rejected_by_api_and_database(client, user):
    response = client.post(
        "/api/v1/auth/register",
        {
            "email": "WALKER@example.com",
            "password": PASSWORD,
            "display_name": "중복",
        },
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="WALKER@EXAMPLE.COM")])


def test_weak_password_and_privilege_injection(client):
    payload = {"email": "other@example.com", "password": "123", "display_name": "다른 사용자"}
    assert client.post("/api/v1/auth/register", payload).status_code == 400
    payload.update(password=PASSWORD, is_staff=True, is_superuser=True)
    assert client.post("/api/v1/auth/register", payload).status_code == 201
    assert not User.objects.get().is_staff


def test_login_refresh_logout_lifecycle(client, user):
    assert (
        client.post("/api/v1/auth/token", {"email": user.email, "password": "wrong"}).status_code
        == 401
    )
    login = client.post("/api/v1/auth/token", {"email": user.email.upper(), "password": PASSWORD})
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert client.get("/api/v1/me").data["id"] == str(user.id)
    refreshed = client.post("/api/v1/auth/token/refresh", {"refresh": login.data["refresh"]})
    assert refreshed.status_code == 200
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": login.data["refresh"]}).status_code
        == 401
    )
    assert (
        client.post("/api/v1/auth/logout", {"refresh": refreshed.data["refresh"]}).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/token/refresh", {"refresh": refreshed.data["refresh"]}
        ).status_code
        == 401
    )
    # Logout does not invalidate already-issued access tokens until their expiry.
    assert client.get("/api/v1/me").status_code == 200


def test_expired_token_and_disabled_account(client, user):
    refresh = RefreshToken.for_user(user)
    access = AccessToken.for_user(user)
    access.set_exp(from_time=timezone.now(), lifetime=timedelta(seconds=-1))
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert client.get("/api/v1/me").status_code == 401
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    user.is_active = False
    user.save()
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/token/refresh", {"refresh": str(refresh)}).status_code == 401
    assert (
        client.post("/api/v1/auth/token", {"email": user.email, "password": PASSWORD}).status_code
        == 401
    )


@pytest.mark.django_db(transaction=True)
def test_simultaneous_refresh_has_one_winner(user):
    refresh = str(RefreshToken.for_user(user))

    def rotate():
        close_old_connections()
        try:
            return APIClient().post("/api/v1/auth/token/refresh", {"refresh": refresh}).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(results) == [200, 401]
