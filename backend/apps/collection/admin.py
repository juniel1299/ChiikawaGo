from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import CollectionEntry


@admin.register(CollectionEntry)
class CollectionEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "character",
        "character_variant",
        "rarity",
        "captured_at",
        "captured_spot",
    )
    readonly_fields = (
        "id",
        "user",
        "character_variant",
        "capture_link",
        "character",
        "rarity",
        "captured_at",
        "captured_spot",
    )
    fields = readonly_fields
    list_select_related = (
        "user",
        "character_variant__character",
        "capture_result__encounter__spot",
    )
    search_fields = ("user__email", "character_variant__name")
    actions = None

    @admin.display(description="Character")
    def character(self, obj):
        return obj.character_variant.character

    @admin.display(description="Rarity")
    def rarity(self, obj):
        return obj.character_variant.rarity

    @admin.display(description="획득 시각", ordering="capture_result__captured_at")
    def captured_at(self, obj):
        return obj.capture_result.captured_at

    @admin.display(description="획득 Spot")
    def captured_spot(self, obj):
        return obj.capture_result.encounter.spot

    @admin.display(description="Capture 결과")
    def capture_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:encounters_captureresult_change", args=[obj.capture_result_id]),
            obj.capture_result_id,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
