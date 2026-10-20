from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Comment, ContentStatus, Post
from .selectors import posts_for
from .serializers import (
    CommentInputSerializer,
    CommentSerializer,
    PostDetailSerializer,
    PostInputSerializer,
    PostListSerializer,
    ReportInputSerializer,
    ReportSerializer,
    StrictInputSerializer,
)


class PostListView(generics.ListAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [JSONParser]
    serializer_class = PostListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Post.objects.none()
        queryset = posts_for(self.request.user)
        if "category" in self.request.query_params:
            serializer = PostInputSerializer(
                data={"category": self.request.query_params["category"]}, partial=True
            )
            serializer.is_valid(raise_exception=True)
            queryset = queryset.filter(category=serializer.validated_data["category"])
        return queryset

    @extend_schema(parameters=[OpenApiParameter("category", str, enum=Post.Category.values)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(request=PostInputSerializer, responses={201: PostDetailSerializer})
    def post(self, request):
        serializer = PostInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = services.create_post(user=request.user, **serializer.validated_data)
        # No relationships exist yet; avoid a second visibility lookup after commit.
        post.like_count = post.comment_count = 0
        post.is_liked = False
        return Response(PostDetailSerializer(post).data, status=201)


class PostDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [JSONParser]

    @extend_schema(responses=PostDetailSerializer)
    def get(self, request, pk):
        return Response(
            PostDetailSerializer(get_object_or_404(posts_for(request.user), pk=pk)).data
        )

    @extend_schema(request=PostInputSerializer, responses=PostDetailSerializer)
    def patch(self, request, pk):
        serializer = PostInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_post(user=request.user, post_id=pk, data=serializer.validated_data)
        return self.get(request, pk)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, pk):
        services.delete_post(user=request.user, post_id=pk)
        return Response(status=204)


class CommentListView(generics.ListAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [JSONParser]
    serializer_class = CommentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Comment.objects.none()
        post = get_object_or_404(Post, pk=self.kwargs["pk"], status=ContentStatus.VISIBLE)
        return (
            Comment.objects.filter(post=post, status=ContentStatus.VISIBLE)
            .select_related("author")
            .order_by("created_at", "id")
        )

    @extend_schema(request=CommentInputSerializer, responses={201: CommentSerializer})
    def post(self, request, pk):
        serializer = CommentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = services.create_comment(
            user=request.user, post_id=pk, **serializer.validated_data
        )
        return Response(CommentSerializer(comment).data, status=201)


class CommentDetailView(APIView):
    parser_classes = [JSONParser]

    @extend_schema(request=CommentInputSerializer, responses=CommentSerializer)
    def patch(self, request, pk):
        serializer = CommentInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        comment = services.update_comment(
            user=request.user, comment_id=pk, data=serializer.validated_data
        )
        return Response(CommentSerializer(comment).data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, pk):
        services.delete_comment(user=request.user, comment_id=pk)
        return Response(status=204)


class LikeView(APIView):
    parser_classes = [JSONParser]

    @extend_schema(request=StrictInputSerializer, responses={204: None})
    def put(self, request, pk):
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_like(user=request.user, post_id=pk, liked=True)
        return Response(status=204)

    @extend_schema(request=StrictInputSerializer, responses={204: None})
    def delete(self, request, pk):
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_like(user=request.user, post_id=pk, liked=False)
        return Response(status=204)


class ReportView(APIView):
    parser_classes = [JSONParser]

    @extend_schema(
        request=ReportInputSerializer, responses={200: ReportSerializer, 201: ReportSerializer}
    )
    def post(self, request):
        serializer = ReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report, created = services.create_report(user=request.user, **serializer.validated_data)
        return Response(ReportSerializer(report).data, status=201 if created else 200)
