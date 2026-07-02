from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from daily_digest.config import ModelConfig


@dataclass
class ModelUsageRecord:
    stage: str
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    raw_usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def usage_record(stage: str, response: dict[str, Any], config: ModelConfig) -> ModelUsageRecord:
    usage = response.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)

    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    cached_input_tokens = int(input_details.get("cached_tokens") or 0)
    reasoning_tokens = int(output_details.get("reasoning_tokens") or 0)

    return ModelUsageRecord(
        stage=stage,
        model=str(response.get("model") or config.model),
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimate_cost_usd(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            config=config,
        ),
        raw_usage=usage,
    )


def estimate_cost_usd(
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    config: ModelConfig,
) -> float | None:
    pricing = config.pricing_usd_per_1m_tokens
    if not pricing:
        return None

    input_rate = pricing.get("input")
    cached_input_rate = pricing.get("cached_input", input_rate)
    output_rate = pricing.get("output")
    if input_rate is None or output_rate is None:
        return None

    uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
    cost = (
        (uncached_input_tokens / 1_000_000) * input_rate
        + (cached_input_tokens / 1_000_000) * cached_input_rate
        + (output_tokens / 1_000_000) * output_rate
    )
    return round(cost, 6)


def usage_summary(records: list[ModelUsageRecord]) -> dict[str, Any]:
    total_cost: float | None = 0.0
    summary = {
        "calls": len(records),
        "input_tokens": sum(record.input_tokens for record in records),
        "cached_input_tokens": sum(record.cached_input_tokens for record in records),
        "output_tokens": sum(record.output_tokens for record in records),
        "reasoning_tokens": sum(record.reasoning_tokens for record in records),
        "total_tokens": sum(record.total_tokens for record in records),
        "estimated_cost_usd": None,
    }

    for record in records:
        if record.estimated_cost_usd is None:
            total_cost = None
            break
        total_cost += record.estimated_cost_usd
    if total_cost is not None:
        summary["estimated_cost_usd"] = round(total_cost, 6)
    return summary


def usage_report(records: list[ModelUsageRecord]) -> dict[str, Any]:
    return {
        "summary": usage_summary(records),
        "calls": [record.to_dict() for record in records],
    }

