from django.core.management.base import BaseCommand, CommandError

from apps.news.crawler import collect
from apps.news.models import Source
from apps.news.parser import CollectionError


class Command(BaseCommand):
    help = "Collect the registered source once, without publishing or scheduling."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)

    def handle(self, *args, **options):
        try:
            source = Source.objects.get(code=options["source"])
            counts = collect(source.pk)
        except (Source.DoesNotExist, CollectionError) as exc:
            raise CommandError("Source unavailable or collection policy check failed.") from exc
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
        if counts["failed"]:
            raise CommandError("Collection incomplete; successful candidates were preserved.")
