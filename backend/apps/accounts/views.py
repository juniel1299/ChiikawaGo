from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    LogoutSerializer,
    RegisterSerializer,
    TokenPairResponseSerializer,
    UserSerializer,
)
from .tokens import locked_refresh_token


@extend_schema_view(post=extend_schema(responses={200: TokenPairResponseSerializer}))
class LoginView(TokenObtainPairView):
    pass


@extend_schema_view(post=extend_schema(responses={200: TokenPairResponseSerializer}))
class RefreshView(TokenRefreshView):
    pass


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = RegisterSerializer


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    # Allow logout even if access has expired. Possession of a refresh permits only its revocation.
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with locked_refresh_token(serializer.validated_data["refresh"]) as token:
                token.blacklist()
        except TokenError as exc:
            raise AuthenticationFailed("유효하지 않은 토큰입니다.") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
