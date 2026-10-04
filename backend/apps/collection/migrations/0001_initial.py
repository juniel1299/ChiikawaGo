import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("characters", "0001_initial"),
        ("encounters", "0002_captureresult_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectionEntry",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "capture_result",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="collection_entry",
                        to="encounters.captureresult",
                    ),
                ),
                (
                    "character_variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="characters.charactervariant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
        ),
    ]
