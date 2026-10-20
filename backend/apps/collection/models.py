import uuid

from django.conf import settings
from django.db import models


class CollectionEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    character_variant = models.ForeignKey("characters.CharacterVariant", on_delete=models.PROTECT)
    capture_result = models.OneToOneField(
        "encounters.CaptureResult", on_delete=models.PROTECT, related_name="collection_entry"
    )
