import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class SpawnRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    spot = models.ForeignKey("spatial.Spot", on_delete=models.PROTECT)
    character_variant = models.ForeignKey("characters.CharacterVariant", on_delete=models.PROTECT)
    weight = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(weight__gt=0), name="spawn_weight_positive"),
            models.CheckConstraint(
                condition=models.Q(starts_at__isnull=True)
                | models.Q(ends_at__isnull=True)
                | models.Q(starts_at__lt=models.F("ends_at")),
                name="spawn_period_valid",
            ),
            models.UniqueConstraint(
                fields=["spot", "character_variant"], name="spawn_spot_variant_unique"
            ),
        ]

    def __str__(self):
        return f"{self.spot}: {self.character_variant}"


class Encounter(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CAPTURED = "captured", "Captured"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    spot = models.ForeignKey("spatial.Spot", on_delete=models.PROTECT)
    character_variant = models.ForeignKey("characters.CharacterVariant", on_delete=models.PROTECT)
    spawned_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("spawned_at")),
                name="encounter_expiry_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["active", "expired", "captured"]),
                name="encounter_status_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "spot"],
                condition=models.Q(status="active"),
                name="encounter_user_spot_active_unique",
            ),
        ]

    def effective_status(self, at=None):
        at = timezone.now() if at is None else at
        if self.status == self.Status.ACTIVE and self.expires_at <= at:
            return self.Status.EXPIRED
        return self.status


class CaptureResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.OneToOneField(
        Encounter, on_delete=models.PROTECT, related_name="capture_result"
    )
    captured_at = models.DateTimeField()
