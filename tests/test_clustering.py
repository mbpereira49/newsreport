from __future__ import annotations

import unittest

from daily_digest.clustering import cluster_items
from daily_digest.models import FetchedItem


def item(title: str, url: str, source: str, summary: str = "", query_set: str | None = None) -> FetchedItem:
    return FetchedItem(
        id=f"{source}-{abs(hash((title, url))) % 100000}",
        title=title,
        url=url,
        source_name=source,
        source_kind="curated_feed",
        fetched_at="2026-07-02T12:00:00+00:00",
        summary=summary,
        published_at="2026-07-02T11:00:00+00:00",
        query_set=query_set,
        metadata={"domain": source.lower().replace(" ", "") + ".example"},
    )


class ClusteringTests(unittest.TestCase):
    def test_near_duplicate_titles_cluster(self) -> None:
        items = [
            item("City approves new housing transit plan", "https://a.example/story", "A"),
            item("New city housing and transit plan approved", "https://b.example/story", "B"),
            item("Astronomers image a distant galaxy", "https://c.example/story", "C"),
        ]

        clusters = cluster_items(items, threshold=0.45)

        self.assertEqual(len(clusters), 2)
        self.assertTrue(any(cluster.source_count == 2 for cluster in clusters))

    def test_exact_url_dedupes(self) -> None:
        items = [
            item("Same story", "https://example.com/story?utm_source=x", "A"),
            item("Same story", "https://www.example.com/story", "A"),
        ]

        clusters = cluster_items(items)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0].items), 1)

    def test_serendipity_property(self) -> None:
        clusters = cluster_items(
            [
                item(
                    "Museum restores lost design archive",
                    "https://arts.example/archive",
                    "Arts",
                    query_set="serendipity",
                )
            ]
        )

        self.assertTrue(clusters[0].is_serendipity)


if __name__ == "__main__":
    unittest.main()

