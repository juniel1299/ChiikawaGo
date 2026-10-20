import re
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from croniter import CroniterBadCronError, CroniterBadDateError, croniter
from rest_framework.exceptions import ValidationError


def validate_schedule(expression, zone, starts_at=None, ends_at=None, now=None):
    if zone not in {"UTC", "Asia/Seoul"}:
        raise ValidationError({"timezone": "서울 또는 UTC만 지원합니다."})
    if (
        len(expression) > 128
        or len(expression.split()) != 5
        or not re.fullmatch(r"[0-9*,/\- ]+", expression)
    ):
        raise ValidationError({"cron_expression": "숫자 기반 5필드 Cron이 필요합니다."})
    if starts_at and ends_at and starts_at >= ends_at:
        raise ValidationError({"ends_at": "시작 이후여야 합니다."})
    from django.utils import timezone

    try:
        croniter(
            expression,
            (now or timezone.now()).astimezone(ZoneInfo(zone)),
            max_years_between_matches=8,
        ).get_next()
    except (CroniterBadCronError, CroniterBadDateError, ValueError, StopIteration) as exc:
        raise ValidationError({"cron_expression": "실행 가능한 Cron이 아닙니다."}) from exc


def next_run(schedule, now):
    if not schedule.enabled or (schedule.ends_at and schedule.ends_at <= now):
        return None
    base = now
    if schedule.starts_at and schedule.starts_at > now:
        base = schedule.starts_at - timedelta(microseconds=1)
    try:
        value = (
            croniter(
                schedule.cron_expression,
                base.astimezone(ZoneInfo(schedule.timezone)),
                max_years_between_matches=8,
            )
            .get_next(type(now))
            .astimezone(UTC)
        )
    except (CroniterBadDateError, StopIteration):
        return None
    return value if not schedule.ends_at or value < schedule.ends_at else None


def latest_due(schedule, now):
    value = (
        croniter(
            schedule.cron_expression,
            (now + timedelta(microseconds=1)).astimezone(ZoneInfo(schedule.timezone)),
            max_years_between_matches=8,
        )
        .get_prev(type(now))
        .astimezone(UTC)
    )
    return value
