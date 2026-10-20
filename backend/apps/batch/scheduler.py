from django.utils import timezone

from .delivery import reconcile
from .models import BatchSchedule
from .services import schedule_due


def tick(now=None):
    now = now or timezone.now()
    for job_id in list(
        BatchSchedule.objects.filter(
            enabled=True, job__enabled=True, next_run_at__lte=now
        ).values_list("job_id", flat=True)
    ):
        schedule_due(job_id, now)
    reconcile(now)
