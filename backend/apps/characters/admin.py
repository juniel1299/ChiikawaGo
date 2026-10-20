from django.contrib import admin

from .models import Character, CharacterVariant


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(CharacterVariant)
class CharacterVariantAdmin(admin.ModelAdmin):
    list_display = ("code", "character", "name", "rarity", "is_active")
    list_filter = ("rarity", "is_active")
    search_fields = ("code", "name", "character__name")
    autocomplete_fields = ("character",)
    list_select_related = ("character",)
