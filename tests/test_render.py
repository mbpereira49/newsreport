from __future__ import annotations

import unittest
from datetime import date

from daily_digest.config import PublicationConfig
from daily_digest.models import FetchedItem, ModuleBlock, StoryCluster
from daily_digest.render import render_html_digest


class HtmlRenderTests(unittest.TestCase):
    def test_html_digest_contains_newspaper_structure(self) -> None:
        item = FetchedItem(
            id="item-1",
            title="A story",
            url="https://example.com/story",
            source_name="Example News",
            source_kind="curated_feed",
            fetched_at="2026-07-02T12:00:00+00:00",
            summary="Summary",
            metadata={"domain": "example.com", "publisher": "Example News"},
        )
        cluster = StoryCluster(
            id="cluster-1",
            title="A story",
            summary="Summary",
            items=[item],
            score=3.0,
        )
        entries = [
            {
                "cluster_id": "cluster-1",
                "headline": "Lead headline",
                "dek": "A sharp summary.",
                "body": "First paragraph.\n\nSecond paragraph.",
                "why_it_matters": "Because it matters.",
                "source_ids": ["cluster-1-s1"],
            }
        ]
        modules = [ModuleBlock(id="note", title="Today", kind="text_file", content={"text": "A note."})]

        rendered = render_html_digest(PublicationConfig(name="Test Daily"), date(2026, 7, 2), entries, [cluster], modules)

        self.assertIn("<!doctype html>", rendered)
        self.assertIn('class="masthead"', rendered)
        self.assertIn("Lead headline", rendered)
        self.assertIn("Example News", rendered)
        self.assertIn("@media print", rendered)


if __name__ == "__main__":
    unittest.main()

