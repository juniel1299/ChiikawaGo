from django.urls import path

from .views import NearbyView

urlpatterns = [path("spots/nearby", NearbyView.as_view())]
