from __future__ import annotations

from daily_digest.config import PublicationConfig
from daily_digest.models import StoryCluster


def deterministic_selection(publication: PublicationConfig, clusters: list[StoryCluster]) -> list[str]:
    selected: list[StoryCluster] = []
    source_counts: dict[str, int] = {}
    serendipity = sorted(
        [cluster for cluster in clusters if cluster.is_serendipity],
        key=_selection_score,
        reverse=True,
    )
    regular = sorted(
        [cluster for cluster in clusters if not cluster.is_serendipity],
        key=_selection_score,
        reverse=True,
    )

    regular_slots = max(publication.max_stories - publication.min_serendipity_stories, 0)
    for cluster in regular:
        if len(selected) >= regular_slots:
            break
        _add_if_allowed(selected, source_counts, cluster, max_per_source=2)
    for cluster in serendipity:
        if len([item for item in selected if item.is_serendipity]) >= publication.min_serendipity_stories:
            break
        _add_if_allowed(selected, source_counts, cluster, max_per_source=2)
    for cluster in regular:
        if len(selected) >= publication.max_stories:
            break
        _add_if_allowed(selected, source_counts, cluster, max_per_source=2)

    for cluster in clusters:
        if len(selected) >= publication.max_stories:
            break
        if cluster.id not in {item.id for item in selected}:
            selected.append(cluster)

    return [cluster.id for cluster in selected[: publication.max_stories]]


def _selection_score(cluster: StoryCluster) -> float:
    excerpt_bonus = 1.0 if any(len(item.summary.strip()) > len(item.title.strip()) + 20 for item in cluster.items) else 0.0
    return cluster.score + excerpt_bonus


def _add_if_allowed(
    selected: list[StoryCluster],
    source_counts: dict[str, int],
    cluster: StoryCluster,
    max_per_source: int,
) -> None:
    if cluster.id in {item.id for item in selected}:
        return
    source = _primary_source(cluster)
    if source_counts.get(source, 0) >= max_per_source:
        return
    selected.append(cluster)
    source_counts[source] = source_counts.get(source, 0) + 1


def _primary_source(cluster: StoryCluster) -> str:
    if not cluster.items:
        return ""
    return cluster.items[0].source_name
