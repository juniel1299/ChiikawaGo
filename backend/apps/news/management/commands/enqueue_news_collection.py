from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from apps.news.enqueue import enqueue_collection
from apps.news.models import Source


class Command(BaseCommand):
    help = "Accept a batch execution; acceptance does not confirm delivery or collection."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)

    def handle(self, *args, **options):
        try:
            source = Source.objects.get(code=options["source"])
            row = enqueue_collection(source.pk)
        except (Source.DoesNotExist, APIException):
            raise CommandError(
                "Source/Batch Job unavailable or another execution is active."
            ) from None
        self.stdout.write(f"accepted execution_id={row.pk} task_id={row.celery_task_id}")
