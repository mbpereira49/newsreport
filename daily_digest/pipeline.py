from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from daily_digest.clustering import cluster_items, filter_fresh_items
from daily_digest.config import PipelineConfig
from daily_digest.fetch.discovery import fetch_discovery
from daily_digest.fetch.rss import FetchError, fetch_feed
from daily_digest.llm import (
    ModelUnavailable,
    OpenAIResponsesClient,
    fallback_entries,
    model_layout_digest,
    model_select_clusters,
    model_synthesize_entries,
)
from daily_digest.models import DigestRun, FetchedItem, utc_now_iso
from daily_digest.modules import load_modules
from daily_digest.render import render_fallback_digest, render_html_digest
from daily_digest.selection import deterministic_selection
from daily_digest.usage import usage_report

ProgressCallback = Callable[[str], None]


def run_digest(
    config: PipelineConfig,
    config_path: Path,
    run_date: date | None = None,
    use_model: bool = True,
    progress: ProgressCallback | None = None,
) -> tuple[Path, DigestRun, list[str]]:
    warnings: list[str] = []
    run_date = run_date or _today(config.publication.timezone)
    _emit(progress, f"Run date: {run_date.isoformat()} ({config.publication.timezone})")
    output_root = Path(config.output_dir)
    if not output_root.is_absolute():
        output_root = Path.cwd() / output_root
    artifact_dir = output_root / run_date.isoformat()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _emit(progress, f"Artifacts directory: {artifact_dir}")

    fetched_items, fetch_warnings = fetch_all(config, run_date, progress)
    warnings.extend(fetch_warnings)
    _write_json(artifact_dir / "fetched_items.json", [item.to_dict() for item in fetched_items])
    _emit(progress, f"Wrote fetched_items.json with {len(fetched_items)} raw items")

    fresh_items = filter_fresh_items(fetched_items, config.freshness_hours)
    _emit(progress, f"Freshness filter: {len(fresh_items)} items within {config.freshness_hours} hours")
    clusters = cluster_items(fresh_items, config.cluster_similarity_threshold)
    _write_json(artifact_dir / "clusters.json", [cluster.to_dict() for cluster in clusters])
    _emit(progress, f"Clustering: {len(clusters)} candidate stories")

    modules = load_modules(config.modules, run_date, config_path.parent)
    _write_json(artifact_dir / "modules.json", [module.to_dict() for module in modules])
    _emit(progress, f"Modules: loaded {len(modules)} configured blocks")

    selected_ids = deterministic_selection(config.publication, clusters)
    _emit(progress, f"Deterministic preselection: {len(selected_ids)} stories")
    client: OpenAIResponsesClient | None = None
    if use_model:
        try:
            client = OpenAIResponsesClient(config.model)
            _emit(progress, f"Model selection: sending {min(len(clusters), 40)} clusters to {config.model.model}")
            selected_ids = model_select_clusters(client, config.publication, run_date.isoformat(), clusters)
            _emit(progress, f"Model selection: returned {len(selected_ids)} story ids")
        except ModelUnavailable as exc:
            warnings.append(f"Model selection skipped: {exc}")
            _emit(progress, "Model selection skipped; using deterministic preselection")
    else:
        _emit(progress, "Model calls disabled; using deterministic selection and fallback text")

    selected_clusters = [cluster for cluster in clusters if cluster.id in selected_ids]
    selected_clusters.sort(key=lambda cluster: selected_ids.index(cluster.id))
    entries = fallback_entries(selected_clusters)
    _emit(progress, f"Fallback entries: prepared {len(entries)} entries")

    if use_model and client is not None:
        try:
            _emit(progress, f"Model synthesis: sending {len(selected_clusters)} selected clusters")
            entries = model_synthesize_entries(client, config.publication, run_date.isoformat(), selected_clusters)
            _emit(progress, f"Model synthesis: returned {len(entries)} entries")
        except ModelUnavailable as exc:
            warnings.append(f"Model synthesis skipped: {exc}")
            _emit(progress, "Model synthesis skipped; keeping fallback entries")
    _write_json(artifact_dir / "entries.json", entries)

    digest_markdown = render_fallback_digest(config.publication, run_date, entries, selected_clusters, modules)
    if use_model and client is not None:
        try:
            _emit(progress, "Model layout: generating Markdown edition")
            candidate = model_layout_digest(client, config.publication, run_date.isoformat(), entries, selected_clusters, modules)
            if candidate:
                digest_markdown = candidate.strip() + "\n"
                _emit(progress, "Model layout: Markdown edition returned")
        except ModelUnavailable as exc:
            warnings.append(f"Model layout skipped: {exc}")
            _emit(progress, "Model layout skipped; using fallback Markdown")

    digest_path = output_root / f"{run_date.isoformat()}-digest.md"
    digest_path.write_text(digest_markdown, encoding="utf-8")
    _emit(progress, f"Wrote Markdown: {digest_path}")
    html_path = output_root / f"{run_date.isoformat()}-digest.html"
    html_path.write_text(
        render_html_digest(config.publication, run_date, entries, selected_clusters, modules),
        encoding="utf-8",
    )
    _emit(progress, f"Wrote HTML: {html_path}")

    model_usage = usage_report(client.usage_records) if client is not None else usage_report([])
    _write_json(artifact_dir / "model_usage.json", model_usage)
    if model_usage["summary"]["calls"]:
        summary = model_usage["summary"]
        _emit(
            progress,
            "Model usage: "
            f"{summary['input_tokens']} input, "
            f"{summary['output_tokens']} output, "
            f"{summary['total_tokens']} total tokens",
        )

    digest_run = DigestRun(
        run_date=run_date.isoformat(),
        generated_at=utc_now_iso(),
        items=fresh_items,
        clusters=clusters,
        modules=modules,
        selected_cluster_ids=selected_ids,
        model_usage=model_usage,
    )
    _write_json(artifact_dir / "run.json", digest_run.to_dict())
    warnings_path = artifact_dir / "warnings.txt"
    if warnings:
        warnings_path.write_text("\n".join(warnings) + "\n", encoding="utf-8")
        _emit(progress, f"Warnings: wrote {len(warnings)} warning(s)")
    elif warnings_path.exists():
        warnings_path.unlink()

    return digest_path, digest_run, warnings


def fetch_all(
    config: PipelineConfig,
    run_date: date,
    progress: ProgressCallback | None = None,
) -> tuple[list[FetchedItem], list[str]]:
    warnings: list[str] = []
    items: list[FetchedItem] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        _emit(progress, f"Fetching: {len(config.curated_feeds)} curated feeds")
        for feed in config.curated_feeds:
            future = executor.submit(
                fetch_feed,
                feed.name,
                feed.url,
                "curated_feed",
                feed.tags,
                max_items=feed.max_items,
            )
            futures[future] = feed.name
        if config.discovery.enabled:
            discovery_count = len(config.discovery.query_sets) * 2 + min(
                config.discovery.serendipity_per_day,
                len(config.discovery.serendipity_queries),
            )
            _emit(progress, f"Fetching: discovery layer enabled (~{discovery_count} rotating queries)")
            futures[
                executor.submit(fetch_discovery, config.discovery, run_date)
            ] = "discovery searches"

        for future in as_completed(futures):
            label = futures[future]
            try:
                result = future.result()
                items.extend(result)
                _emit(progress, f"Fetched {len(result):>3} item(s) from {label}")
            except (FetchError, ValueError, OSError) as exc:
                warnings.append(str(exc))
                _emit(progress, f"Fetch warning from {label}: {exc}")

    return items, warnings


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _today(timezone_name: str) -> date:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).date()


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True, sort_keys=True), encoding="utf-8")
