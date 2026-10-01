import uuid

import pytest
from django.contrib.gis.geos import Point
from django.db import IntegrityError, connection, transaction

from apps.spatial.admin import SpotForm
from apps.spatial.models import Spot
from apps.spatial.selectors import nearby_spots

pytestmark = pytest.mark.django_db
ORIGIN = {"latitude": 37.5665, "longitude": 126.978}


def projected_point(meters):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsText(ST_Project("
            "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,0)::geometry)",
            [ORIGIN["longitude"], ORIGIN["latitude"], meters],
        )
        return Point.from_ewkt("SRID=4326;" + cursor.fetchone()[0])


def test_nearby_filters_and_stable_order(authenticated):
    for index, meters in enumerate([0, 100, 999, 1001]):
        Spot.objects.create(code=f"spot-{index}", name="장소", location=projected_point(meters))
    Spot.objects.create(code="hidden", name="비공개", location=projected_point(10), is_active=False)
    response = authenticated.get("/api/v1/spots/nearby", ORIGIN)
    assert response.status_code == 200
    assert response.data["count"] == 3
    results = response.data["results"]
    assert [row["code"] for row in results] == ["spot-0", "spot-1", "spot-2"]
    assert results[1]["distance_m"] == pytest.approx(100, abs=0.001)
    assert results[0]["location"] == ORIGIN
    same = Spot.objects.create(
        id=uuid.UUID(int=1), code="same", name="동일 거리", location=projected_point(0)
    )
    assert authenticated.get("/api/v1/spots/nearby", ORIGIN).data["results"][0]["id"] == str(
        same.pk
    )
    assert (
        authenticated.get("/api/v1/spots/nearby", {"latitude": 0, "longitude": 0}).data["count"]
        == 0
    )


def test_boundary_uses_same_postgis_distance(authenticated):
    Spot.objects.create(code="edge", name="경계", location=projected_point(1000))
    distance = nearby_spots(**ORIGIN, radius_m=1100).first().distance.m
    assert (
        authenticated.get("/api/v1/spots/nearby", {**ORIGIN, "radius_m": distance + 0.0001}).data[
            "count"
        ]
        == 1
    )
    assert (
        authenticated.get("/api/v1/spots/nearby", {**ORIGIN, "radius_m": distance - 0.0001}).data[
            "count"
        ]
        == 0
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", 126.978),
        ("longitude", 181),
        ("latitude", "NaN"),
        ("radius_m", "Infinity"),
        ("radius_m", 0),
        ("radius_m", -1),
        ("radius_m", 5001),
    ],
)
def test_invalid_query(authenticated, field, value):
    assert authenticated.get("/api/v1/spots/nearby", {**ORIGIN, field: value}).status_code == 400


def test_nearby_auth_required_and_missing_coordinates(client, authenticated):
    from rest_framework.test import APIClient

    assert APIClient().get("/api/v1/spots/nearby", ORIGIN).status_code == 401
    assert authenticated.get("/api/v1/spots/nearby").status_code == 400


def test_admin_input_and_radius_constraint():
    form = SpotForm(
        data={
            "code": "seoul",
            "name": "서울",
            **ORIGIN,
            "interaction_radius_m": 100,
            "is_active": True,
        }
    )
    assert form.is_valid(), form.errors
    spot = form.save()
    assert (spot.location.x, spot.location.y) == (126.978, 37.5665)
    with pytest.raises(IntegrityError), transaction.atomic():
        Spot.objects.filter(pk=spot.pk).update(interaction_radius_m=0)


def test_postgis_index_and_query_shape():
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'spatial_spot'")
        assert any("USING gist (location)" in row[0] for row in cursor.fetchall())
    sql = str(nearby_spots(**ORIGIN, radius_m=1000).query)
    assert "ST_DWithin" in sql
    assert "ST_Distance" in sql
