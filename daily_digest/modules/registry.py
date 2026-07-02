from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from daily_digest.models import ModuleBlock, stable_id


def load_modules(module_configs: list[dict[str, Any]], run_date: date, config_dir: Path) -> list[ModuleBlock]:
    blocks: list[ModuleBlock] = []
    for module_config in module_configs:
        kind = module_config.get("type")
        if kind == "calendar_json":
            blocks.append(_calendar_json(module_config, run_date, config_dir))
        elif kind == "text_file":
            blocks.append(_text_file(module_config, config_dir))
        elif kind:
            blocks.append(
                ModuleBlock(
                    id=stable_id(kind, module_config.get("title", kind)),
                    title=module_config.get("title", kind.replace("_", " ").title()),
                    kind=kind,
                    content={"status": "unsupported", "config": module_config},
                    rendered_hint="Unsupported module type; include only as a note if useful.",
                )
            )
    return blocks


def _resolve_path(config_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config_dir / path


def _calendar_json(module_config: dict[str, Any], run_date: date, config_dir: Path) -> ModuleBlock:
    path = _resolve_path(config_dir, module_config["path"])
    if not path.exists():
        events: list[dict[str, Any]] = []
    else:
        with path.open("r", encoding="utf-8") as fh:
            raw_events = json.load(fh)
        events = [
            event
            for event in raw_events
            if str(event.get("date", "")).startswith(run_date.isoformat())
            or str(event.get("start", "")).startswith(run_date.isoformat())
        ]

    title = module_config.get("title", "Today")
    return ModuleBlock(
        id=stable_id("calendar_json", title, run_date.isoformat()),
        title=title,
        kind="calendar_json",
        content={"date": run_date.isoformat(), "events": events},
        rendered_hint="Brief calendar sidebar or short agenda block, only if there are events.",
    )


def _text_file(module_config: dict[str, Any], config_dir: Path) -> ModuleBlock:
    path = _resolve_path(config_dir, module_config["path"])
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    title = module_config.get("title", path.stem.replace("_", " ").title())
    return ModuleBlock(
        id=stable_id("text_file", str(path), title),
        title=title,
        kind="text_file",
        content={"text": content},
        rendered_hint=module_config.get("rendered_hint", "Optional non-news block."),
    )

