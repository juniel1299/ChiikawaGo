from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from apps.batch.services import finish_attempt, request_run, run_attempt
from apps.news.enqueue import configured_job
from apps.news.models import Source


class Command(BaseCommand):
    help = "Collect synchronously through the batch ledger, without broker or automatic retry."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)

    def handle(self, *args, **options):
        try:
            source = Source.objects.get(code=options["source"])
            execution, _ = request_run(job_id=configured_job(source.pk).pk, key=uuid4(), sync=True)
        except (Source.DoesNotExist, APIException):
            raise CommandError(
                "Source/Batch Job unavailable or another execution is active."
            ) from None
        outcome = run_attempt(execution)
        row = finish_attempt(execution.pk, 1, outcome)
        counts = outcome.counts or {"created": 0, "skipped": 0, "failed": 1}
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
        if row.status != "success":
            raise CommandError("Collection incomplete; successful candidates were preserved.")
