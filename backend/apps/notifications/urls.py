from django.urls import path

from .views import DeviceView, ResolveView

urlpatterns = [
    path("notifications/devices/<uuid:installation_id>", DeviceView.as_view()),
    path("notifications/devices/<uuid:installation_id>/resolve", ResolveView.as_view()),
]
