from __future__ import annotations

import argparse
import os
from datetime import date, datetime
from pathlib import Path

from daily_digest.config import load_config
from daily_digest.pipeline import run_digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Produce a personalized daily digest.")
    parser.add_argument("--config", default="config/digest.example.json", help="Path to the digest JSON config.")
    parser.add_argument("--date", help="Run date in YYYY-MM-DD format. Defaults to today in publication timezone.")
    parser.add_argument("--no-model", action="store_true", help="Skip model calls and render the deterministic fallback digest.")
    parser.add_argument("--quiet", action="store_true", help="Only print the final summary and warnings.")
    return parser


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    load_dotenv(Path(".env"))
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    run_date = date.fromisoformat(args.date) if args.date else None
    progress = None if args.quiet else print_progress
    if not args.quiet:
        print(f"Starting digest run with config {config_path}")
    digest_path, digest_run, warnings = run_digest(
        config,
        config_path,
        run_date,
        use_model=not args.no_model,
        progress=progress,
    )

    html_path = digest_path.with_suffix(".html")
    print(f"Wrote {html_path}")
    print(f"Wrote {digest_path}")
    print(f"Fetched {len(digest_run.items)} fresh items into {len(digest_run.clusters)} clusters.")
    print(f"Selected {len(digest_run.selected_cluster_ids)} clusters.")
    usage = digest_run.model_usage.get("summary", {})
    if usage.get("calls"):
        print(
            "Model usage: "
            f"{usage.get('input_tokens', 0)} input, "
            f"{usage.get('output_tokens', 0)} output, "
            f"{usage.get('total_tokens', 0)} total tokens."
        )
        if usage.get("estimated_cost_usd") is not None:
            print(f"Estimated model spend: ${usage['estimated_cost_usd']:.6f}")
    for warning in warnings:
        print(f"Warning: {warning}")
    return 0


def print_progress(message: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
