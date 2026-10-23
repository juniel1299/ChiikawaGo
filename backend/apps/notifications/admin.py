import uuid

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from .models import PushDelivery, PushDevice, PushMessage
from .services import can_send, request_test


class ReadOnly(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PushDevice)
class DeviceAdmin(ReadOnly):
    exclude = ("provider_token", "token_hash", "secret_hash")
    list_display = ("id", "user", "platform", "enabled", "binding_version", "last_registered_at")
    list_select_related = ("user",)


class SendForm(forms.Form):
    target_user = forms.ModelChoiceField(queryset=get_user_model().objects.filter(is_active=True))
    key = forms.UUIDField(widget=forms.HiddenInput)


@admin.register(PushMessage)
class MessageAdmin(ReadOnly):
    list_display = ("id", "target_user", "requested_at", "test_send")
    list_select_related = ("target_user",)
    change_list_template = "admin/notifications/message_list.html"

    @admin.display(description="테스트 발송")
    def test_send(self, obj):
        return format_html('<a href="{}">새 테스트 발송</a>', reverse("admin:push_test_send"))

    def get_urls(self):
        return [
            path("test-send/", self.admin_site.admin_view(self.send_view), name="push_test_send")
        ] + super().get_urls()

    def send_view(self, request):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        if not can_send(request.user) or not self.has_view_permission(request):
            raise PermissionDenied()
        form = SendForm(
            request.POST if request.method == "POST" else None, initial={"key": uuid.uuid4()}
        )
        if request.method == "POST" and form.is_valid():
            try:
                message = request_test(
                    operator=request.user,
                    target_user_id=form.cleaned_data["target_user"].pk,
                    key=form.cleaned_data["key"],
                )
            except APIException:
                form.add_error(None, "접수할 수 없습니다. 활성 기기와 요청 키를 확인해 주세요.")
            else:
                self.log_change(request, message, "OPERATOR_TEST requested")
                return HttpResponseRedirect(
                    reverse("admin:notifications_pushmessage_change", args=[message.pk])
                )
        return TemplateResponse(
            request,
            "admin/notifications/send.html",
            {
                **self.admin_site.each_context(request),
                "title": "운영자 테스트 알림",
                "form": form,
            },
        )


@admin.register(PushDelivery)
class DeliveryAdmin(ReadOnly):
    list_display = ("id", "message", "device", "status", "attempt", "failure_code", "requested_at")
    list_filter = ("status",)
    list_select_related = ("message", "device")
