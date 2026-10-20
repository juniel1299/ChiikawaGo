from django.urls import path

from .views import CharacterDetailView, CharacterListView, VariantListView

urlpatterns = [
    path("characters", CharacterListView.as_view()),
    path("characters/<uuid:pk>", CharacterDetailView.as_view()),
    path("characters/<uuid:pk>/variants", VariantListView.as_view()),
]
