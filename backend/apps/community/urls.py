from django.urls import path

from .views import (
    CommentDetailView,
    CommentListView,
    LikeView,
    PostDetailView,
    PostListView,
    ReportView,
)

urlpatterns = [
    path("community/posts", PostListView.as_view()),
    path("community/posts/<uuid:pk>", PostDetailView.as_view()),
    path("community/posts/<uuid:pk>/comments", CommentListView.as_view()),
    path("community/comments/<uuid:pk>", CommentDetailView.as_view()),
    path("community/posts/<uuid:pk>/like", LikeView.as_view()),
    path("community/reports", ReportView.as_view()),
]
