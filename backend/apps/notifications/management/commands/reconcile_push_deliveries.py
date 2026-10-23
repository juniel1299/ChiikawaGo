import time

from django.core.management.base import BaseCommand

from apps.notifications.delivery import reconcile


class Command(BaseCommand):
    help = "Recover notification dispatch only; never re-send UNKNOWN deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            reconcile()
            if options["once"]:
                return
            time.sleep(5)
