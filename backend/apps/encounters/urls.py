from django.urls import path

from .views import CaptureView, EncounterCreateView, EncounterDetailView

urlpatterns = [
    path("encounters/<uuid:pk>/capture", CaptureView.as_view()),
    path("encounters", EncounterCreateView.as_view()),
    path("encounters/<uuid:pk>", EncounterDetailView.as_view()),
]
