from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: str) -> str:
    payload = "\n".join(part.strip() for part in parts if part).encode("utf-8")
    return sha1(payload).hexdigest()[:16]


@dataclass
class SourceRef:
    id: str
    name: str
    url: str
    domain: str
    publisher: str
    title: str
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchedItem:
    id: str
    title: str
    url: str
    source_name: str
    source_kind: str
    fetched_at: str
    summary: str = ""
    published_at: str | None = None
    query: str | None = None
    query_set: str | None = None
    ranking_weight: float = 1.0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoryCluster:
    id: str
    title: str
    summary: str
    items: list[FetchedItem]
    score: float
    tags: list[str] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len({item.source_name for item in self.items})

    @property
    def is_serendipity(self) -> bool:
        return any(item.query_set == "serendipity" for item in self.items)

    def source_refs(self) -> list[SourceRef]:
        refs: list[SourceRef] = []
        seen: set[tuple[str, str]] = set()
        for idx, item in enumerate(self.items, start=1):
            publisher = item.metadata.get("publisher", item.source_name)
            key = (publisher, item.url)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                SourceRef(
                    id=f"{self.id}-s{idx}",
                    name=publisher,
                    url=item.url,
                    domain=item.metadata.get("domain", ""),
                    publisher=publisher,
                    title=item.title,
                    published_at=item.published_at,
                )
            )
        return refs

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_count"] = self.source_count
        data["is_serendipity"] = self.is_serendipity
        data["source_refs"] = [ref.to_dict() for ref in self.source_refs()]
        return data


@dataclass
class ModuleBlock:
    id: str
    title: str
    kind: str
    content: dict[str, Any]
    rendered_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DigestRun:
    run_date: str
    generated_at: str
    items: list[FetchedItem]
    clusters: list[StoryCluster]
    modules: list[ModuleBlock]
    selected_cluster_ids: list[str] = field(default_factory=list)
    model_usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_date": self.run_date,
            "generated_at": self.generated_at,
            "items": [item.to_dict() for item in self.items],
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "modules": [module.to_dict() for module in self.modules],
            "selected_cluster_ids": self.selected_cluster_ids,
            "model_usage": self.model_usage,
        }
