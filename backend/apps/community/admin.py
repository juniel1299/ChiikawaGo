from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from .models import Comment, Post, Report
from .services import moderate_content, review_report


class CommunityAdmin(admin.ModelAdmin):
    """Read-only records with explicit, CSRF-protected moderation commands."""

    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields] + ["moderation_links"]

    @admin.display(description="운영 조치")
    def moderation_links(self, obj):
        name = self.model._meta.model_name
        return format_html(
            '<a href="{}">조치 확인 화면</a>',
            reverse(f"admin:community_{name}_moderate", args=[obj.pk]),
        )

    def get_urls(self):
        name = self.model._meta.model_name
        return [
            path(
                "<uuid:pk>/moderate/",
                self.admin_site.admin_view(self.moderate_view),
                name=f"community_{name}_moderate",
            )
        ] + super().get_urls()

    def moderate_view(self, request, pk):
        obj = self.get_object(request, str(pk))
        if obj is None or not self.has_view_permission(request, obj):
            raise PermissionDenied
        name = self.model._meta.model_name
        permission = "review_report" if name == "report" else f"moderate_{name}"
        if not request.user.has_perm(f"community.{permission}"):
            raise PermissionDenied
        error, status = None, 200
        if request.method == "POST":
            action = request.POST.get("action")
            try:
                if name == "report":
                    review_report(user=request.user, report_id=pk, status=action)
                elif action in ("hide", "restore"):
                    moderate_content(
                        user=request.user, target_type=name, target_id=pk, hidden=action == "hide"
                    )
                else:
                    return TemplateResponse(
                        request,
                        "admin/community/moderate.html",
                        {"error": "잘못된 조치입니다."},
                        status=400,
                    )
            except APIException as exc:
                # Never echo arbitrary submitted values or report evidence.
                error, status = (
                    "조치를 수행할 수 없습니다. 권한과 현재 상태를 확인하세요.",
                    exc.status_code,
                )
            else:
                return HttpResponseRedirect(reverse(f"admin:community_{name}_change", args=[pk]))
        return TemplateResponse(
            request,
            "admin/community/moderate.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": "운영 조치 확인",
                "object_id": str(pk),
                "error": error,
                "report": name == "report",
            },
            status=status,
        )


@admin.register(Post)
class PostAdmin(CommunityAdmin):
    list_display = ("id", "author", "category", "status", "created_at")
    list_filter = ("status", "category")
    list_select_related = ("author",)


@admin.register(Comment)
class CommentAdmin(CommunityAdmin):
    list_display = ("id", "post", "author", "status", "created_at")
    list_filter = ("status",)
    list_select_related = ("post", "author")


@admin.register(Report)
class ReportAdmin(CommunityAdmin):
    list_display = (
        "id",
        "target_type",
        "target_id",
        "reason",
        "status",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("status", "reason")
    list_select_related = ("reporter", "post", "comment", "reviewed_by")
