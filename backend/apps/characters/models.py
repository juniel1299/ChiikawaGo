import uuid

from django.db import models


class Character(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class CharacterVariant(models.Model):
    class Rarity(models.TextChoices):
        COMMON = "common", "Common"
        RARE = "rare", "Rare"
        EPIC = "epic", "Epic"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    character = models.ForeignKey(Character, on_delete=models.PROTECT, related_name="variants")
    code = models.SlugField()
    name = models.CharField(max_length=100)
    rarity = models.CharField(max_length=10, choices=Rarity.choices, default=Rarity.COMMON)
    asset_key = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["character", "code"], name="variant_character_code_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(rarity__in=["common", "rare", "epic"]),
                name="variant_rarity_valid",
            ),
        ]

    def __str__(self):
        return f"{self.character}: {self.name}"
