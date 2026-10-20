from django.core.management.base import BaseCommand

from apps.batch.models import BatchJob


class Command(BaseCommand):
    help = "Register disabled allowlisted jobs without schedules; preserve existing configuration."

    def handle(self, *args, **options):
        for code, name in BatchJob.Code.choices:
            _, created = BatchJob.objects.get_or_create(code=code, defaults={"name": name})
            self.stdout.write(f"{code}: {'created_disabled' if created else 'unchanged'}")
