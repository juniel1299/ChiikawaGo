from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken


def clean_expired_tokens(*, cutoff=None, batch_size=500):
    cutoff = cutoff or timezone.now()
    counts = {"outstanding_deleted": 0, "blacklisted_deleted": 0}
    while True:
        with transaction.atomic():
            ids = list(
                OutstandingToken.objects.filter(expires_at__lte=cutoff)
                .order_by("pk")
                .select_for_update(skip_locked=True)
                .values_list("pk", flat=True)[:batch_size]
            )
            if not ids:
                return counts
            _, deleted = OutstandingToken.objects.filter(pk__in=ids).delete()
            counts["outstanding_deleted"] += deleted.get("token_blacklist.OutstandingToken", 0)
            counts["blacklisted_deleted"] += deleted.get("token_blacklist.BlacklistedToken", 0)
