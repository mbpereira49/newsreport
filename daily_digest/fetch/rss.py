from __future__ import annotations

import email.utils
import socket
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable

from daily_digest.models import FetchedItem, stable_id, utc_now_iso
from daily_digest.text import canonical_url, clean_html, domain_from_url


ATOM_NS = "{http://www.w3.org/2005/Atom}"


class FetchError(RuntimeError):
    pass


class DigestRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_302(req, fp, code, msg, headers)


def fetch_url(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PersonalDailyDigest/0.1 (+https://example.local)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )
    opener = urllib.request.build_opener(DigestRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read()
    except (OSError, socket.timeout) as exc:
        raise FetchError(f"Could not fetch {url}: {exc}") from exc


def parse_rss_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _child_text(parent: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        node = parent.find(name)
        if node is not None and node.text:
            return clean_html(node.text)
    return ""


def _atom_link(entry: ET.Element) -> str:
    for link in entry.findall(f"{ATOM_NS}link"):
        href = link.attrib.get("href")
        rel = link.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
    return ""


def parse_feed(
    payload: bytes,
    source_name: str,
    source_kind: str,
    source_url: str,
    tags: list[str] | None = None,
    ranking_weight: float = 1.0,
    query: str | None = None,
    query_set: str | None = None,
    max_items: int | None = None,
) -> list[FetchedItem]:
    try:
        root = ET.fromstring(payload.lstrip(b"\xef\xbb\xbf \t\r\n"))
    except ET.ParseError as exc:
        raise FetchError(f"Could not parse feed {source_url}: {exc}") from exc
    fetched_at = utc_now_iso()
    parsed_items: list[FetchedItem] = []
    tags = tags or []

    if root.tag == f"{ATOM_NS}feed":
        entries = root.findall(f"{ATOM_NS}entry")
        for entry in entries[:max_items]:
            title = _child_text(entry, [f"{ATOM_NS}title"])
            url = _atom_link(entry)
            summary = _child_text(entry, [f"{ATOM_NS}summary", f"{ATOM_NS}content"])
            published = _child_text(entry, [f"{ATOM_NS}published", f"{ATOM_NS}updated"])
            published_at = parse_rss_datetime(published) or published or None
            parsed_items.append(
                _make_item(
                    title,
                    url,
                    source_name,
                    source_kind,
                    source_url,
                    fetched_at,
                    summary,
                    published_at,
                    tags,
                    ranking_weight,
                    query,
                    query_set,
                )
            )
        return [item for item in parsed_items if item.title and item.url]

    rss_items = root.findall("./channel/item")
    for item in rss_items[:max_items]:
        title = _child_text(item, ["title"])
        url = _child_text(item, ["link", "guid"])
        summary = _child_text(item, ["description"])
        published_at = parse_rss_datetime(_child_text(item, ["pubDate", "published", "updated"]))
        publisher_node = item.find("source")
        publisher = clean_html(publisher_node.text) if publisher_node is not None and publisher_node.text else None
        publisher_url = publisher_node.attrib.get("url") if publisher_node is not None else None
        parsed_items.append(
            _make_item(
                title,
                url,
                source_name,
                source_kind,
                source_url,
                fetched_at,
                summary,
                published_at,
                tags,
                ranking_weight,
                query,
                query_set,
                publisher,
                publisher_url,
            )
        )
    return [item for item in parsed_items if item.title and item.url]


def _make_item(
    title: str,
    url: str,
    source_name: str,
    source_kind: str,
    source_url: str,
    fetched_at: str,
    summary: str,
    published_at: str | None,
    tags: list[str],
    ranking_weight: float,
    query: str | None,
    query_set: str | None,
    publisher: str | None = None,
    publisher_url: str | None = None,
) -> FetchedItem:
    canon = canonical_url(url)
    display_source = publisher if source_kind == "discovery_search" and publisher else source_name
    domain = domain_from_url(publisher_url or canon)
    return FetchedItem(
        id=stable_id(canon, title),
        title=title,
        url=canon,
        source_name=display_source,
        source_kind=source_kind,
        fetched_at=fetched_at,
        summary=summary,
        published_at=published_at,
        query=query,
        query_set=query_set,
        ranking_weight=ranking_weight,
        tags=list(tags),
        metadata={
            "domain": domain,
            "publisher": display_source,
            "source_url": source_url,
            "publisher_url": publisher_url,
        },
    )


def fetch_feed(
    source_name: str,
    url: str,
    source_kind: str = "curated_feed",
    tags: list[str] | None = None,
    ranking_weight: float = 1.0,
    query: str | None = None,
    query_set: str | None = None,
    max_items: int | None = None,
    timeout: int = 20,
) -> list[FetchedItem]:
    payload = fetch_url(url, timeout=timeout)
    return parse_feed(payload, source_name, source_kind, url, tags, ranking_weight, query, query_set, max_items)
