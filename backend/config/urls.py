from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from config.health import health, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    path("ready", ready),
    path("api/v1/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.characters.urls")),
    path("api/v1/", include("apps.spatial.urls")),
]
handler404 = "config.api.not_found"
handler500 = "config.api.server_error"
