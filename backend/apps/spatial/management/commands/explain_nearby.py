import uuid

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.spatial.models import Spot
from apps.spatial.selectors import nearby_spots


class Command(BaseCommand):
    help = "EXPLAIN ANALYZE with temporary sample spots; sample inserts are always rolled back."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10000)

    def handle(self, *args, **options):
        count = options["count"]
        if not 1 <= count <= 100000:
            raise CommandError("count must be between 1 and 100000")
        prefix = f"explain-{uuid.uuid4().hex[:12]}"
        with transaction.atomic():
            Spot.objects.bulk_create(
                [
                    Spot(
                        code=f"{prefix}-{i}",
                        name="Temporary query sample",
                        location=Point(
                            126.878 + (i % 100) * 0.002, 37.4665 + (i // 100) * 0.002, srid=4326
                        ),
                    )
                    for i in range(count)
                ],
                batch_size=1000,
            )
            with connection.cursor() as cursor:
                cursor.execute("ANALYZE spatial_spot")
            query = nearby_spots(latitude=37.5665, longitude=126.978, radius_m=1000)
            self.stdout.write(query[:20].explain(analyze=True, buffers=True))
            self.stdout.write(f"Matched: {query.count()}; temporary rows: {count} (rolled back)")
            transaction.set_rollback(True)
