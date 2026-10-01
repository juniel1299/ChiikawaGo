import uuid

from django.contrib.gis.db import models
from django.core.exceptions import ValidationError


class Spot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.PointField(srid=4326, geography=True, spatial_index=True)
    interaction_radius_m = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(interaction_radius_m__gt=0),
                name="spot_radius_positive",
            )
        ]

    def clean(self):
        super().clean()
        if self.location and not (-180 <= self.location.x <= 180 and -90 <= self.location.y <= 90):
            raise ValidationError({"location": "경도·위도 범위를 확인하세요."})

    def __str__(self):
        return self.name
