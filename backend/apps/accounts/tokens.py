from contextlib import contextmanager

from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken


@contextmanager
def locked_refresh_token(raw_token):
    token = RefreshToken(raw_token)
    with transaction.atomic():
        try:
            OutstandingToken.objects.select_for_update().get(jti=token["jti"])
        except OutstandingToken.DoesNotExist as exc:
            raise TokenError("Outstanding token does not exist") from exc
        # A competing request may have revoked the token while we waited.
        yield RefreshToken(raw_token)
