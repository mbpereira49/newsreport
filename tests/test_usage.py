from __future__ import annotations

import unittest

from daily_digest.config import ModelConfig
from daily_digest.usage import estimate_cost_usd, usage_record, usage_summary


class UsageTests(unittest.TestCase):
    def test_estimates_cost_with_cached_input_tokens(self) -> None:
        config = ModelConfig(
            pricing_usd_per_1m_tokens={
                "input": 5.0,
                "cached_input": 0.5,
                "output": 30.0,
            }
        )

        cost = estimate_cost_usd(
            input_tokens=10_000,
            cached_input_tokens=4_000,
            output_tokens=2_000,
            config=config,
        )

        self.assertEqual(cost, 0.092)

    def test_usage_record_extracts_response_usage(self) -> None:
        config = ModelConfig(pricing_usd_per_1m_tokens={"input": 5.0, "cached_input": 0.5, "output": 30.0})
        response = {
            "model": "gpt-5.5-2026-07-01",
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 20},
                "output_tokens": 10,
                "output_tokens_details": {"reasoning_tokens": 3},
                "total_tokens": 110,
            },
        }

        record = usage_record("digest_selection", response, config)

        self.assertEqual(record.stage, "digest_selection")
        self.assertEqual(record.cached_input_tokens, 20)
        self.assertEqual(record.reasoning_tokens, 3)
        self.assertEqual(record.total_tokens, 110)
        self.assertIsNotNone(record.estimated_cost_usd)

    def test_usage_summary_marks_cost_unknown_without_pricing(self) -> None:
        record = usage_record("digest_selection", {"usage": {"input_tokens": 100}}, ModelConfig())

        summary = usage_summary([record])

        self.assertIsNone(summary["estimated_cost_usd"])


if __name__ == "__main__":
    unittest.main()

