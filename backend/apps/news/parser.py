"""Small, source-specific parser. HTML is transient and never persisted."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .models import DREAMNEWS_LIST

ORIGIN = "https://www.dreamnews.jp"
COMPANY_PATH = "/company/0000014066"


class CollectionError(Exception):
    """Safe fixed error codes only; never include a response body or arbitrary URL."""


@dataclass(frozen=True)
class Item:
    external_id: str
    canonical_url: str
    title: str
    published_at: datetime

    @property
    def metadata_hash(self):
        value = json.dumps(
            [self.external_id, self.canonical_url, self.title, self.published_at.isoformat()],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode()).hexdigest()


def validate_url(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "www.dreamnews.jp"
        or parts.query
        or parts.fragment
    ):
        raise CollectionError("url_not_allowed")
    if parts.path not in ("/robots.txt", COMPANY_PATH, COMPANY_PATH + "/") and not re.fullmatch(
        r"/press/[0-9]{10}/?", parts.path
    ):
        raise CollectionError("path_not_allowed")
    return url


def canonicalize(url):
    validate_url(url)
    match = re.fullmatch(r"/press/([0-9]{10})/?", urlsplit(url).path)
    if not match:
        raise CollectionError("invalid_detail_url")
    return f"{ORIGIN}/press/{match[1]}"


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.links = []
        self.anchor = None
        self.items = []
        self.seen_feed = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self.depth:
                self.depth += 1
            elif "feedItem" in attrs.get("class", "").split():
                self.depth = 1
                self.seen_feed = True
                self.links = []
        if self.depth and tag == "a":
            self.anchor = [attrs.get("href", ""), ""]

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.links.append(self.anchor)
            self.anchor = None
        if tag == "div" and self.depth:
            self.depth -= 1
            if not self.depth:
                company = any(
                    urljoin(ORIGIN, href).rstrip("/") == DREAMNEWS_LIST.rstrip("/")
                    for href, _ in self.links
                )
                if company:
                    for href, title in self.links:
                        if "ちいかわ" in title:
                            self.items.append(canonicalize(urljoin(ORIGIN, href)))


def parse_listing(html):
    parser = ListingParser()
    parser.feed(html)
    if not parser.seen_feed or parser.depth:
        raise CollectionError("listing_structure_changed")
    return list(dict.fromkeys(parser.items))[:5]


class DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonicals = []
        self.scripts = []
        self.script = None
        self.heading = None
        self.headings = []
        self.company = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonicals.append(attrs.get("href", ""))
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.script = ""
        if tag == "h1":
            self.heading = ""
        if tag == "a" and urljoin(ORIGIN, attrs.get("href", "")).rstrip(
            "/"
        ) == DREAMNEWS_LIST.rstrip("/"):
            self.company = True

    def handle_data(self, data):
        if self.script is not None:
            self.script += data
        if self.heading is not None:
            self.heading += data

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append(self.script)
            self.script = None
        if tag == "h1" and self.heading is not None:
            self.headings.append(self.heading.strip())
            self.heading = None


def parse_detail(html, url):
    expected = canonicalize(url)
    parser = DetailParser()
    parser.feed(html)
    try:
        if len(parser.canonicals) != 1 or canonicalize(parser.canonicals[0]) != expected:
            raise CollectionError("canonical_mismatch")
        entries = []
        for script in parser.scripts:
            data = json.loads(script)
            entries.extend(data if isinstance(data, list) else data.get("@graph", [data]))
        articles = [entry for entry in entries if entry.get("@type") in ("Article", "NewsArticle")]
        if len(articles) != 1:
            raise CollectionError("article_metadata_missing")
        data = articles[0]
        external_id = expected.rsplit("/", 1)[1]
        if str(data["identifier"]) != external_id or canonicalize(data["url"]) != expected:
            raise CollectionError("identifier_mismatch")
        title = data["headline"].strip()
        author = data["author"]
        if (
            not parser.company
            or author.get("name") != "株式会社ドリテック"
            or title not in parser.headings
            or "ちいかわ" not in title
            or len(title) > 500
        ):
            raise CollectionError("article_metadata_mismatch")
        published = datetime.fromisoformat(data["datePublished"])
        if published.tzinfo is None:
            raise CollectionError("date_timezone_missing")
        return Item(external_id, expected, title, published.astimezone(UTC))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CollectionError("invalid_article_metadata") from exc
