from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

from .models import Spot


def nearby_spots(*, latitude, longitude, radius_m):
    origin = Point(longitude, latitude, srid=4326)
    return (
        Spot.objects.filter(is_active=True, location__dwithin=(origin, D(m=radius_m)))
        .annotate(distance=Distance("location", origin))
        .order_by("distance", "id")
    )
