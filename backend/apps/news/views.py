from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Category, News
from .serializers import NewsFilterSerializer, NewsSerializer


class NewsListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsSerializer
    queryset = (
        News.objects.filter(candidate__status="published")
        .select_related("source")
        .order_by("-published_at", "-id")
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        serializer = NewsFilterSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        return queryset.filter(**serializer.validated_data)

    @extend_schema(parameters=[OpenApiParameter("category", str, enum=Category.values)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class NewsDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsSerializer
    queryset = News.objects.filter(candidate__status="published").select_related("source")
