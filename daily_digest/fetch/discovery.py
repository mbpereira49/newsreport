from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus

from daily_digest.config import DiscoveryConfig
from daily_digest.fetch.rss import fetch_feed
from daily_digest.models import FetchedItem


def google_news_search_url(query: str, locale: str, region: str) -> str:
    language = locale.split("-")[0]
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={locale}&gl={region}&ceid={region}:{language}"
    )


def discovery_queries(config: DiscoveryConfig, run_date: date) -> list[tuple[str, str, list[str], float]]:
    queries: list[tuple[str, str, list[str], float]] = []
    day_ordinal = run_date.toordinal()

    for query_set in config.query_sets:
        if not query_set.queries:
            continue
        rotation_count = min(2, len(query_set.queries))
        for offset in range(rotation_count):
            index = (day_ordinal + offset) % len(query_set.queries)
            queries.append((query_set.name, query_set.queries[index], query_set.tags, query_set.weight))

    if config.serendipity_queries:
        count = min(config.serendipity_per_day, len(config.serendipity_queries))
        for offset in range(count):
            index = (day_ordinal + offset * 7) % len(config.serendipity_queries)
            queries.append(("serendipity", config.serendipity_queries[index], ["serendipity"], 0.8))

    return queries


def fetch_discovery(config: DiscoveryConfig, run_date: date) -> list[FetchedItem]:
    if not config.enabled:
        return []
    if config.provider != "google_news_rss":
        raise ValueError(f"Unsupported discovery provider: {config.provider}")

    items: list[FetchedItem] = []
    for query_set, query, tags, weight in discovery_queries(config, run_date):
        url = google_news_search_url(query, config.locale, config.region)
        items.extend(
            fetch_feed(
                source_name=f"Google News search: {query}",
                url=url,
                source_kind="discovery_search",
                tags=tags,
                ranking_weight=weight,
                query=query,
                query_set=query_set,
                max_items=config.max_items_per_query,
            )
        )
    return items
