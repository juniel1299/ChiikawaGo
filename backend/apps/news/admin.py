from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from .models import News, NewsCandidate, RawItem, Source
from .services import review_candidate


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "policy_checked_at")
    readonly_fields = ("next_request_at", "created_at", "updated_at")
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (("code", "adapter_key", "base_url") if obj else ())

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            current = Source.objects.select_for_update(no_key=True).get(pk=obj.pk)
            # An operator edit must not overwrite a concurrent crawler reservation.
            obj.next_request_at = current.next_request_at
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(RawItem)
class RawItemAdmin(ReadOnlyAdmin):
    list_display = ("id", "source", "external_id", "published_at", "collected_at")
    list_select_related = ("source",)


@admin.register(News)
class NewsAdmin(ReadOnlyAdmin):
    list_display = ("id", "title", "category", "source", "published_at", "created_at")
    list_filter = ("category", "source")
    list_select_related = ("source", "candidate")


@admin.register(NewsCandidate)
class CandidateAdmin(ReadOnlyAdmin):
    list_display = ("id", "title", "status", "reviewed_at")
    list_filter = ("status",)
    list_select_related = ("raw_item__source", "reviewed_by")

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + ["review_link", "source_link"]

    @admin.display(description="출처")
    def source_link(self, obj):
        return format_html(
            '<a href="{}" rel="noreferrer">원문 확인</a>', obj.raw_item.canonical_url
        )

    @admin.display(description="검수")
    def review_link(self, obj):
        return format_html(
            '<a href="{}">승인/반려 확인</a>', reverse("admin:news_review", args=[obj.pk])
        )

    def get_urls(self):
        return [
            path(
                "<uuid:pk>/review/",
                self.admin_site.admin_view(self.review_view),
                name="news_review",
            )
        ] + super().get_urls()

    def review_view(self, request, pk):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        obj = self.get_object(request, str(pk))
        if (
            obj is None
            or not self.has_view_permission(request, obj)
            or not request.user.has_perm("news.review_newscandidate")
        ):
            raise PermissionDenied
        error, status = None, 200
        if request.method == "POST":
            try:
                review_candidate(
                    user=request.user, candidate_id=pk, action=request.POST.get("action")
                )
            except APIException as exc:
                error, status = "권한·현재 상태·출처 정책을 확인하세요.", exc.status_code
            else:
                return HttpResponseRedirect(reverse("admin:news_newscandidate_change", args=[pk]))
        return TemplateResponse(
            request,
            "admin/news/review.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": "News 검수",
                "candidate": obj,
                "error": error,
            },
            status=status,
        )
