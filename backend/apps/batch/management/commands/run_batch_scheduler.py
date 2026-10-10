import signal
import time
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.batch.scheduler import tick
from config.error_logging import log_internal_exception


class Command(BaseCommand):
    help = "Poll database schedules and recover pending delivery; no source-code cron."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        stopping = False

        def stop(*args):
            nonlocal stopping
            stopping = True

        if not options["once"]:
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
        while not stopping:
            close_old_connections()
            try:
                tick()
                Path("/tmp/batch-scheduler-heartbeat").touch()
            except Exception as exc:
                log_internal_exception(exc, SimpleNamespace(request_id="batch-scheduler"))
                if options["once"]:
                    raise
            if options["once"]:
                return
            time.sleep(5)
