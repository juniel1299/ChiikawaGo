from django.urls import path

from .views import LoginView, LogoutView, MeView, RefreshView, RegisterView

urlpatterns = [
    path("auth/register", RegisterView.as_view()),
    path("auth/token", LoginView.as_view()),
    path("auth/token/refresh", RefreshView.as_view()),
    path("auth/logout", LogoutView.as_view()),
    path("me", MeView.as_view()),
]
