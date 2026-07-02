from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from daily_digest.models import FetchedItem, StoryCluster, stable_id
from daily_digest.text import canonical_url, jaccard, tokens


def filter_fresh_items(items: list[FetchedItem], freshness_hours: int, now: datetime | None = None) -> list[FetchedItem]:
    if freshness_hours <= 0:
        return items
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=freshness_hours)
    fresh: list[FetchedItem] = []
    for item in items:
        published = _parse_iso(item.published_at)
        if published is None or published >= cutoff:
            fresh.append(item)
    return fresh


def cluster_items(items: list[FetchedItem], threshold: float = 0.5) -> list[StoryCluster]:
    unique = _dedupe_exact(items)
    token_cache = {item.id: tokens(f"{item.title} {item.summary}") for item in unique}
    parent = {item.id: item.id for item in unique}
    by_url: dict[str, list[FetchedItem]] = defaultdict(list)

    for item in unique:
        by_url[canonical_url(item.url)].append(item)
    for same_url_items in by_url.values():
        for item in same_url_items[1:]:
            _union(parent, same_url_items[0].id, item.id)

    for idx, left in enumerate(unique):
        for right in unique[idx + 1 :]:
            similarity = jaccard(token_cache[left.id], token_cache[right.id])
            title_similarity = jaccard(tokens(left.title), tokens(right.title))
            if similarity >= threshold or title_similarity >= max(threshold, 0.62):
                _union(parent, left.id, right.id)

    grouped: dict[str, list[FetchedItem]] = defaultdict(list)
    for item in unique:
        grouped[_find(parent, item.id)].append(item)

    clusters = [_make_cluster(group) for group in grouped.values()]
    return sorted(clusters, key=lambda cluster: cluster.score, reverse=True)


def _dedupe_exact(items: list[FetchedItem]) -> list[FetchedItem]:
    seen: set[tuple[str, str]] = set()
    unique: list[FetchedItem] = []
    for item in items:
        key = (canonical_url(item.url), item.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _make_cluster(items: list[FetchedItem]) -> StoryCluster:
    sorted_items = sorted(
        items,
        key=lambda item: (item.ranking_weight, item.published_at or item.fetched_at, len(item.summary)),
        reverse=True,
    )
    lead = sorted_items[0]
    source_diversity = len({item.metadata.get("domain") or item.source_name for item in sorted_items})
    query_sets = {item.query_set for item in sorted_items if item.query_set}
    curated_count = sum(1 for item in sorted_items if item.source_kind == "curated_feed")
    ranking_total = sum(item.ranking_weight for item in sorted_items)
    score = ranking_total + source_diversity * 1.5 + curated_count * 0.75 + min(len(query_sets), 3) * 0.5
    tags = sorted({tag for item in sorted_items for tag in item.tags})
    return StoryCluster(
        id=stable_id(lead.title, *(item.url for item in sorted_items[:4])),
        title=lead.title,
        summary=lead.summary,
        items=sorted_items,
        score=round(score, 3),
        tags=tags,
    )


def _find(parent: dict[str, str], item_id: str) -> str:
    while parent[item_id] != item_id:
        parent[item_id] = parent[parent[item_id]]
        item_id = parent[item_id]
    return item_id


def _union(parent: dict[str, str], left: str, right: str) -> None:
    root_left = _find(parent, left)
    root_right = _find(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
