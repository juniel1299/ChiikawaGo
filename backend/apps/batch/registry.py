from dataclasses import dataclass

from apps.accounts.cleanup import clean_expired_tokens
from apps.news import crawler


@dataclass(frozen=True)
class Outcome:
    counts: dict
    errors: tuple = ()
    retryable: bool = False


def collect_news(snapshot):
    result = crawler.collect(snapshot["source_id"])
    return Outcome(
        result.counts,
        tuple({"code": e.code, "stage": e.stage} for e in result.errors),
        result.retryable,
    )


def cleanup_tokens(snapshot):
    return Outcome(clean_expired_tokens())


# DB values never become Python import paths.
HANDLERS = {"news_collection": collect_news, "expired_token_cleanup": cleanup_tokens}
POLICIES = {
    "news_collection": {"soft_limit": 600, "hard_limit": 660, "max_retries": 2},
    "expired_token_cleanup": {"soft_limit": 600, "hard_limit": 660, "max_retries": 0},
}
