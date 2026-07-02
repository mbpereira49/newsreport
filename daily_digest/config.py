from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PublicationConfig:
    name: str = "Daily Brief"
    timezone: str = "America/Los_Angeles"
    tone: str = "curious, concise, lightly editorial, never press-release-like"
    target_length_words: int = 1400
    formality: str = "smart magazine"
    max_stories: int = 8
    min_serendipity_stories: int = 1


@dataclass
class FeedConfig:
    name: str
    url: str
    tags: list[str] = field(default_factory=list)
    max_items: int = 10


@dataclass
class QuerySetConfig:
    name: str
    queries: list[str]
    tags: list[str] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class DiscoveryConfig:
    enabled: bool = True
    provider: str = "google_news_rss"
    locale: str = "en-US"
    region: str = "US"
    max_items_per_query: int = 8
    query_sets: list[QuerySetConfig] = field(default_factory=list)
    serendipity_queries: list[str] = field(default_factory=list)
    serendipity_per_day: int = 2


@dataclass
class ModelConfig:
    provider: str = "openai"
    model: str = "gpt-5.5"
    timeout_seconds: int = 60
    temperature: float | None = None
    pricing_usd_per_1m_tokens: dict[str, float] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    publication: PublicationConfig
    freshness_hours: int
    curated_feeds: list[FeedConfig]
    discovery: DiscoveryConfig
    modules: list[dict[str, Any]]
    model: ModelConfig
    output_dir: str
    cluster_similarity_threshold: float = 0.5


def load_config(path: str | Path) -> PipelineConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    publication = PublicationConfig(**raw.get("publication", {}))
    feeds = [FeedConfig(**feed) for feed in raw.get("curated_feeds", [])]

    discovery_raw = raw.get("discovery", {})
    query_sets = [QuerySetConfig(**query_set) for query_set in discovery_raw.get("query_sets", [])]
    discovery = DiscoveryConfig(
        enabled=discovery_raw.get("enabled", True),
        provider=discovery_raw.get("provider", "google_news_rss"),
        locale=discovery_raw.get("locale", "en-US"),
        region=discovery_raw.get("region", "US"),
        max_items_per_query=discovery_raw.get("max_items_per_query", 8),
        query_sets=query_sets,
        serendipity_queries=discovery_raw.get("serendipity_queries", []),
        serendipity_per_day=discovery_raw.get("serendipity_per_day", 2),
    )

    return PipelineConfig(
        publication=publication,
        freshness_hours=raw.get("freshness_hours", 36),
        curated_feeds=feeds,
        discovery=discovery,
        modules=raw.get("modules", []),
        model=ModelConfig(**raw.get("model", {})),
        output_dir=raw.get("output_dir", "out"),
        cluster_similarity_threshold=raw.get("cluster_similarity_threshold", 0.5),
    )
