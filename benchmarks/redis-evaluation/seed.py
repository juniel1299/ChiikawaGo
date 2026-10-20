# ruff: noqa: E402
# Django must initialize before importing app models.
"""Only the isolated chii_perf database may be populated."""

import os
import random
import sys
import uuid

sys.path.insert(0, "/app")
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
import django

django.setup()
from django.contrib.gis.geos import Point
from django.db import connection

from apps.accounts.models import User
from apps.characters.models import Character, CharacterVariant
from apps.news.models import News, NewsCandidate, RawItem, Source
from apps.spatial.models import Spot

assert connection.settings_dict["NAME"] == "chii_perf"
scale = int(os.environ.get("PERF_SCALE", "1"))
assert scale in (1, 10)
rng = random.Random(20261016)


def uid(kind, i):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"chii-perf/{kind}/{i}")


u, _ = User.objects.get_or_create(
    email="perf@example.invalid", defaults={"display_name": "Synthetic"}
)
u.set_unusable_password()
u.save()
# Repeatable clean data, only within the explicitly isolated DB.
News.objects.all().delete()
NewsCandidate.objects.all().delete()
RawItem.objects.all().delete()
CharacterVariant.objects.all().delete()
Character.objects.all().delete()
Spot.objects.all().delete()
for start in range(0, 10000 * scale, 1000):
    rows = []
    for i in range(start, start + 1000):
        # 50% dense 2km square, 30% regional 20km, 20% sparse 200km.
        spread = 0.01 if i % 10 < 5 else (0.1 if i % 10 < 8 else 1)
        rows.append(
            Spot(
                id=uid("spot", i),
                code=f"perf-{i:07}",
                name=f"Synthetic {i}",
                location=Point(
                    127 + rng.uniform(-spread, spread), 37 + rng.uniform(-spread, spread), srid=4326
                ),
                is_active=i % 10 != 9,
            )
        )
    Spot.objects.bulk_create(rows)
chars = [
    Character(
        id=uid("character", i), code=f"perf-{i:05}", name=f"Character {i}", is_active=i % 10 != 9
    )
    for i in range(100 * scale)
]
Character.objects.bulk_create(chars)
CharacterVariant.objects.bulk_create(
    [
        CharacterVariant(
            id=uid("variant", i),
            character_id=chars[i // 5].pk,
            code=f"v{i % 5}",
            name=f"Variant {i}",
        )
        for i in range(500 * scale)
    ]
)
s, _ = Source.objects.get_or_create(
    code="synthetic", defaults={"name": "Synthetic source", "is_active": False}
)
base = datetime(2026, 1, 1, tzinfo=UTC)
for start in range(0, 10000 * scale, 1000):
    raw = []
    candidates = []
    news = []
    for i in range(start, start + 1000):
        ts = base + timedelta(minutes=i // 2)
        title = f"Synthetic item {i}"
        url = f"https://example.invalid/{i}"
        cat = ["goods", "news", "event", "collaboration"][i % 4]
        raw.append(
            RawItem(
                id=uid("raw", i),
                source=s,
                external_id=str(i),
                canonical_url=url,
                title=title,
                published_at=ts,
                metadata_hash="0" * 64,
            )
        )
        candidates.append(
            NewsCandidate(
                id=uid("candidate", i),
                raw_item_id=uid("raw", i),
                title=title,
                category=cat,
                status="published",
                reviewed_by=u,
                reviewed_at=ts,
            )
        )
        news.append(
            News(
                id=uid("news", i),
                candidate_id=uid("candidate", i),
                source=s,
                source_url=url,
                title=title,
                category=cat,
                published_at=ts,
            )
        )
    RawItem.objects.bulk_create(raw)
    NewsCandidate.objects.bulk_create(candidates)
    News.objects.bulk_create(news)
with connection.cursor() as c:
    c.execute("ANALYZE")
print(
    {
        "seed": 20261016,
        "scale": scale,
        "spots": Spot.objects.count(),
        "characters": Character.objects.count(),
        "variants": CharacterVariant.objects.count(),
        "news": News.objects.count(),
    }
)
