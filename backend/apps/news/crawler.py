"""Synchronous, bounded fetches. No network I/O inside database transactions."""

import socket
import ssl
import time
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from django.db import transaction
from django.utils import timezone

from .models import DREAMNEWS_LIST, Source
from .parser import CollectionError, parse_detail, parse_listing, validate_url
from .results import CollectionResult, TransientCollectionError
from .services import require_source, store_item

USER_AGENT = "ChiiWorldNewsBot/0.1 (+https://github.com/juniel1299/ChiikawaGo)"
MAX_BYTES = 2 * 1024 * 1024
INTERVAL_SECONDS = 10
ROBOTS_URL = "https://www.dreamnews.jp/robots.txt"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@transaction.atomic
def reserve_request(source_id):
    source = Source.objects.select_for_update(no_key=True).get(pk=source_id)
    require_source(source)
    now = timezone.now()
    if source.next_request_at and source.next_request_at > now:
        return (source.next_request_at - now).total_seconds()
    source.next_request_at = now + timedelta(seconds=INTERVAL_SECONDS)
    source.save(update_fields=["next_request_at"])
    return 0


def fetch(source_id, url, *, robots=None):
    original_path = urlsplit(validate_url(url)).path.rstrip("/")
    opener = build_opener(NoRedirect())
    for redirect in range(4):
        validate_url(url)
        # Redirects may canonicalize a path, but cannot change the requested resource.
        if urlsplit(url).path.rstrip("/") != original_path:
            raise CollectionError("redirect_target_changed")
        if robots is not None and not robots.can_fetch(USER_AGENT, url):
            raise CollectionError("robots_denied")
        while delay := reserve_request(source_id):
            time.sleep(delay)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        try:
            with opener.open(request, timeout=10) as response:
                if response.status != 200:
                    raise CollectionError("http_status")
                if response.headers.get("cf-mitigated") == "challenge":
                    raise CollectionError("access_challenge")
                expected_type = "text/plain" if original_path == "/robots.txt" else "text/html"
                if response.headers.get_content_type() != expected_type:
                    raise CollectionError("unexpected_content_type")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise CollectionError("unexpected_content_encoding")
                content = response.read(MAX_BYTES + 1)
                if len(content) > MAX_BYTES:
                    raise CollectionError("response_too_large")
                return content.decode("utf-8-sig")
        except HTTPError as exc:
            location = exc.headers.get("Location")
            status = exc.code
            exc.close()
            if status in (301, 302, 303, 307, 308) and location and redirect < 3:
                url = urljoin(url, location)
                continue
            raise CollectionError(f"http_{status}") from None
        except (URLError, TimeoutError, OSError, UnicodeError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if not isinstance(reason, ssl.SSLError):
                if isinstance(reason, TimeoutError):
                    raise TransientCollectionError("network_timeout") from None
                if isinstance(reason, (ConnectionResetError, ConnectionRefusedError)):
                    raise TransientCollectionError("network_connection") from None
                if isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN:
                    raise TransientCollectionError("network_dns_temporary") from None
            raise CollectionError("fetch_failed") from None
    raise CollectionError("redirect_limit")


def parse_robots(text):
    """Accept only rules whose semantics urllib.robotparser can enforce faithfully."""
    if "<" in text or not text.strip():
        raise CollectionError("invalid_robots")
    seen_agent = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise CollectionError("unsupported_robots")
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key not in ("user-agent", "allow", "disallow", "sitemap", "crawl-delay"):
            raise CollectionError("unsupported_robots")
        if key == "user-agent":
            seen_agent = True
        if key in ("allow", "disallow") and (not seen_agent or "*" in value or "$" in value):
            raise CollectionError("unsupported_robots")
        if key == "crawl-delay" and (not value.isdigit() or int(value) > INTERVAL_SECONDS):
            raise CollectionError("unsupported_crawl_delay")
    if not seen_agent:
        raise CollectionError("invalid_robots")
    # Overlapping Allow/Disallow rules have different precedence in common robots parsers.
    # This first source has an empty Disallow; stop rather than guess if Allow rules appear.
    if any(line.strip().lower().startswith("allow:") for line in text.splitlines()):
        raise CollectionError("unsupported_robots")
    robots = RobotFileParser(ROBOTS_URL)
    robots.parse(text.splitlines())
    return robots


def collect(source_id):
    result = CollectionResult()
    stage = "source"
    try:
        source = Source.objects.get(pk=source_id)
        require_source(source)
        stage = "robots"
        robots = parse_robots(fetch(source_id, ROBOTS_URL))
        stage = "listing_fetch"
        html = fetch(source_id, DREAMNEWS_LIST, robots=robots)
        stage = "listing_parse"
        urls = parse_listing(html)
    except Source.DoesNotExist:
        result.fail(CollectionError("source_missing"), stage)
        return result
    except CollectionError as exc:
        result.fail(exc, stage)
        return result
    for url in urls:
        try:
            stage = "detail_fetch"
            html = fetch(source_id, url, robots=robots)
            stage = "detail_parse"
            item = parse_detail(html, url)
            stage = "store"
            _, created = store_item(source_id=source_id, item=item)
            if created:
                result.created += 1
            else:
                result.skipped += 1
        except CollectionError as exc:
            result.fail(exc, stage)
            # Access failures stop this run; malformed individual articles do not.
            if str(exc).startswith(("http_", "access_", "robots_", "source_")):
                break
    return result
