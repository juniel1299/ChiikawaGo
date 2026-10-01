from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.characters.models import Character, CharacterVariant
from apps.spatial.models import Spot


class Command(BaseCommand):
    help = (
        "Create minimal local demo catalog/spot; never creates users or overwrites existing data."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        character, _ = Character.objects.get_or_create(
            code="demo-character",
            defaults={"name": "샘플 캐릭터", "description": "개발용 카탈로그"},
        )
        CharacterVariant.objects.get_or_create(
            character=character,
            code="default",
            defaults={"name": "기본형"},
        )
        Spot.objects.get_or_create(
            code="demo-seoul",
            defaults={"name": "서울 샘플 Spot", "location": Point(126.978, 37.5665, srid=4326)},
        )
        self.stdout.write(
            self.style.SUCCESS("Demo catalog and spot are ready. Existing data preserved.")
        )
