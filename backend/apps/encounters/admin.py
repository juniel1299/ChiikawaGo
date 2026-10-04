from django.contrib import admin
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import CaptureResult, Encounter, SpawnRule


@admin.register(SpawnRule)
class SpawnRuleAdmin(admin.ModelAdmin):
    list_display = ("spot", "character_variant", "weight", "is_active", "starts_at", "ends_at")
    list_filter = ("is_active",)
    search_fields = ("spot__code", "spot__name", "character_variant__name")
    autocomplete_fields = ("spot", "character_variant")
    list_select_related = ("spot", "character_variant__character")
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return ("spot", "character_variant") if obj else ()

    def has_delete_permission(self, request, obj=None):
        return False


class EffectiveStatusFilter(admin.SimpleListFilter):
    title = "실효 상태"
    parameter_name = "effective_status"

    def lookups(self, request, model_admin):
        return Encounter.Status.choices

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == Encounter.Status.ACTIVE:
            return queryset.filter(status=Encounter.Status.ACTIVE, expires_at__gt=now)
        if self.value() == Encounter.Status.EXPIRED:
            return queryset.filter(
                Q(status=Encounter.Status.EXPIRED)
                | Q(status=Encounter.Status.ACTIVE, expires_at__lte=now)
            )
        if self.value() == Encounter.Status.CAPTURED:
            return queryset.filter(status=Encounter.Status.CAPTURED)
        return queryset


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "spot",
        "character_variant",
        "spawned_at",
        "expires_at",
        "effective_state",
    )
    list_filter = (EffectiveStatusFilter,)
    search_fields = ("user__email", "spot__code", "character_variant__name")
    list_select_related = ("user", "spot", "character_variant__character", "capture_result")
    readonly_fields = (
        "capture_link",
        "id",
        "user",
        "spot",
        "character_variant",
        "spawned_at",
        "expires_at",
        "status",
        "effective_state",
    )
    fieldsets = (
        (
            None,
            {
                "fields": readonly_fields,
                "description": (
                    "저장 상태가 active여도 만료 시각이 지나면 이용할 수 없습니다. "
                    "실효 상태를 확인하세요."
                ),
            },
        ),
    )
    actions = None

    @admin.display(description="Capture 결과")
    def capture_link(self, obj):
        result = getattr(obj, "capture_result", None)
        if result is None:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:encounters_captureresult_change", args=[result.pk]),
            result.pk,
        )

    @admin.display(description="실효 상태")
    def effective_state(self, obj):
        return obj.effective_status()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CaptureResult)
class CaptureResultAdmin(admin.ModelAdmin):
    list_display = ("id", "encounter", "captured_at")
    readonly_fields = ("id", "encounter_link", "captured_at", "collection_link")
    fields = readonly_fields
    list_select_related = ("encounter", "collection_entry")
    actions = None

    @admin.display(description="Encounter")
    def encounter_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:encounters_encounter_change", args=[obj.encounter_id]),
            obj.encounter_id,
        )

    @admin.display(description="Collection")
    def collection_link(self, obj):
        entry = getattr(obj, "collection_entry", None)
        if entry is None:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:collection_collectionentry_change", args=[entry.pk]),
            entry.pk,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
