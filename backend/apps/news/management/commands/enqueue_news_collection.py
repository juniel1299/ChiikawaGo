from django.core.management.base import BaseCommand, CommandError

from apps.news.enqueue import EnqueueError, enqueue_collection
from apps.news.models import Source
from apps.news.parser import CollectionError


class Command(BaseCommand):
    help = "Enqueue one source; a task ID confirms publishing, not collection success."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)

    def handle(self, *args, **options):
        try:
            source = Source.objects.get(code=options["source"])
            task_id = enqueue_collection(source.pk)
        except (Source.DoesNotExist, CollectionError, EnqueueError):
            raise CommandError("Source unavailable or broker publishing failed.") from None
        self.stdout.write(f"published task_id={task_id}")
