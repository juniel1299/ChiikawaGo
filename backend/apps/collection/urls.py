from django.urls import path

from .views import CollectionListView

urlpatterns = [path("collection", CollectionListView.as_view())]
