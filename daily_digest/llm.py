from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from daily_digest.config import ModelConfig, PublicationConfig
from daily_digest.models import ModuleBlock, StoryCluster
from daily_digest.selection import deterministic_selection
from daily_digest.usage import ModelUsageRecord, usage_record


class ModelUnavailable(RuntimeError):
    pass


class OpenAIResponsesClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.usage_records: list[ModelUsageRecord] = []
        if not self.api_key:
            raise ModelUnavailable("OPENAI_API_KEY is not set.")

    def json_response(self, stage: str, schema: dict[str, Any], system: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": stage,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        self._add_optional_sampling(payload)
        data = self._post("/responses", payload)
        self._record_usage(stage, data)
        text = extract_response_text(data)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelUnavailable(f"Model returned invalid JSON for {stage}.") from exc
        if not isinstance(parsed, dict):
            raise ModelUnavailable(f"Model returned non-object JSON for {stage}.")
        return parsed

    def text_response(self, stage: str, system: str, user_payload: dict[str, Any]) -> str:
        payload = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
            ],
        }
        self._add_optional_sampling(payload)
        data = self._post("/responses", payload)
        self._record_usage(stage, data)
        return extract_response_text(data).strip()

    def _record_usage(self, stage: str, response: dict[str, Any]) -> None:
        self.usage_records.append(usage_record(stage, response, self.config))

    def _add_optional_sampling(self, payload: dict[str, Any]) -> None:
        if self.config.temperature is not None:
            payload["temperature"] = self.config.temperature

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            raise ModelUnavailable(f"OpenAI request failed: HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelUnavailable(f"OpenAI request failed: {exc}") from exc


def extract_response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for output in response.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def model_select_clusters(
    client: OpenAIResponsesClient,
    publication: PublicationConfig,
    run_date: str,
    clusters: list[StoryCluster],
) -> list[str]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "cluster_id": {"type": "string"},
                        "role": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["cluster_id", "role", "rationale"],
                },
            }
        },
        "required": ["selected"],
    }
    system = (
        "You are the assigning editor for a personalized daily digest. "
        "Select a diverse set of clusters using only the supplied fetched metadata. "
        "Prefer independent source diversity and include deliberate serendipity. "
        "Do not add facts or stories that are not in the payload."
    )
    payload = {
        "run_date": run_date,
        "publication": asdict(publication),
        "cluster_candidates": [_cluster_brief(cluster) for cluster in clusters[:40]],
    }
    data = client.json_response("digest_selection", schema, system, payload)
    valid_ids = {cluster.id for cluster in clusters}
    selected = [item["cluster_id"] for item in data.get("selected", []) if item.get("cluster_id") in valid_ids]
    if not selected:
        return deterministic_selection(publication, clusters)
    return selected[: publication.max_stories]


def model_synthesize_entries(
    client: OpenAIResponsesClient,
    publication: PublicationConfig,
    run_date: str,
    clusters: list[StoryCluster],
) -> list[dict[str, Any]]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "cluster_id": {"type": "string"},
                        "headline": {"type": "string"},
                        "dek": {"type": "string"},
                        "body": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["cluster_id", "headline", "dek", "body", "why_it_matters", "source_ids"],
                },
            }
        },
        "required": ["entries"],
    }
    system = (
        "You are a sharp digest writer. Synthesize each cluster into an edited entry, "
        "not a neutral feed summary. Use only supplied source excerpts and metadata. "
        "Name uncertainty when sources frame the story differently. Cite source_ids "
        "from the payload; do not invent source_ids."
    )
    payload = {
        "run_date": run_date,
        "publication": asdict(publication),
        "clusters": [_cluster_full(cluster) for cluster in clusters],
    }
    data = client.json_response("digest_entries", schema, system, payload)
    valid_cluster_ids = {cluster.id for cluster in clusters}
    valid_source_ids = {source.id for cluster in clusters for source in cluster.source_refs()}
    entries: list[dict[str, Any]] = []
    for entry in data.get("entries", []):
        if entry.get("cluster_id") not in valid_cluster_ids:
            continue
        entry["source_ids"] = [source_id for source_id in entry.get("source_ids", []) if source_id in valid_source_ids]
        entries.append(entry)
    return entries or fallback_entries(clusters)


def model_layout_digest(
    client: OpenAIResponsesClient,
    publication: PublicationConfig,
    run_date: str,
    entries: list[dict[str, Any]],
    clusters: list[StoryCluster],
    modules: list[ModuleBlock],
) -> str:
    system = (
        "You are the editor and designer of a personalized daily newspaper. "
        "Produce polished Markdown. Keep the publication recognizable, but vary "
        "section order and grouping when today's material calls for it. Use only "
        "the supplied entries and modules. Include source links as Markdown references "
        "near each entry. The voice should match the configured tone, avoiding dry "
        "press-release phrasing."
    )
    payload = {
        "run_date": run_date,
        "publication": asdict(publication),
        "entries": entries,
        "source_catalog": [
            source.to_dict()
            for cluster in clusters
            for source in cluster.source_refs()
        ],
        "modules": [module.to_dict() for module in modules],
    }
    return client.text_response("digest_layout", system, payload)


def fallback_entries(clusters: list[StoryCluster]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for cluster in clusters:
        refs = cluster.source_refs()
        headline = _clean_feed_headline(cluster.title, refs)
        summary = _clean_feed_summary(cluster.summary, headline, refs)
        dek, body = _fallback_dek_body(summary)
        source_count = cluster.source_count
        source_word = "source" if source_count == 1 else "sources"
        tags = ", ".join(cluster.tags[:3])
        why = f"Flagged from {source_count} {source_word}"
        if tags:
            why += f" in {tags}"
        why += "."
        entries.append(
            {
                "cluster_id": cluster.id,
                "headline": headline,
                "dek": dek,
                "body": body,
                "why_it_matters": why,
                "source_ids": [ref.id for ref in refs[:3]],
            }
        )
    return entries


def _clean_feed_headline(title: str, refs: list) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    for ref in refs:
        publisher = re.escape(ref.publisher)
        cleaned = re.sub(rf"\s+[-|]\s+{publisher}$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+[-|]\s+[A-Z][A-Za-z0-9 .&'’]+$", "", cleaned)
    return cleaned or "Untitled"


def _clean_feed_summary(summary: str, headline: str, refs: list) -> str:
    cleaned = re.sub(r"\s+", " ", summary or "").strip()
    if not cleaned:
        return ""
    publishers = {ref.publisher.strip().lower() for ref in refs if ref.publisher}
    if cleaned.lower() in publishers:
        return ""
    if cleaned.lower() == headline.lower():
        return ""
    if cleaned.lower().startswith(headline.lower()):
        cleaned = cleaned[len(headline) :].strip(" .-:|")
    if cleaned.lower() in publishers:
        return ""
    for publisher in publishers:
        cleaned = re.sub(rf"\s+[-|]?\s*{re.escape(publisher)}$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+Tags:\s+.*$", "", cleaned, flags=re.IGNORECASE).strip()
    if cleaned.lower() in publishers:
        return ""
    return cleaned[:320].strip()


def _fallback_dek_body(summary: str) -> tuple[str, str]:
    if not summary:
        return "", ""
    sentences = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)
    dek = sentences[0].strip()
    body = sentences[1].strip() if len(sentences) > 1 else ""
    if len(dek) > 220:
        dek = dek[:217].rstrip() + "..."
        body = ""
    return dek, body


def _cluster_brief(cluster: StoryCluster) -> dict[str, Any]:
    return {
        "id": cluster.id,
        "title": cluster.title,
        "summary": cluster.summary[:500],
        "score": cluster.score,
        "source_count": cluster.source_count,
        "is_serendipity": cluster.is_serendipity,
        "tags": cluster.tags,
        "sources": [
            {
                "name": item.source_name,
                "domain": item.metadata.get("domain", ""),
                "title": item.title,
                "published_at": item.published_at,
                "query_set": item.query_set,
            }
            for item in cluster.items[:5]
        ],
    }


def _cluster_full(cluster: StoryCluster) -> dict[str, Any]:
    return {
        **_cluster_brief(cluster),
        "sources": [
            {
                "source_id": ref.id,
                "name": ref.name,
                "domain": ref.domain,
                "title": ref.title,
                "url": ref.url,
                "published_at": ref.published_at,
                "excerpt": cluster.items[idx].summary[:700] if idx < len(cluster.items) else "",
            }
            for idx, ref in enumerate(cluster.source_refs())
        ],
    }
