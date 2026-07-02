from __future__ import annotations

import unittest

from daily_digest.fetch.rss import parse_feed


class RssParsingTests(unittest.TestCase):
    def test_parse_rss_item(self) -> None:
        payload = b"""<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <title>Example</title>
            <item>
              <title>Story title</title>
              <link>https://example.com/story?utm_campaign=x</link>
              <description>&lt;p&gt;Short summary&lt;/p&gt;</description>
              <pubDate>Thu, 02 Jul 2026 12:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""

        items = parse_feed(payload, "Example", "curated_feed", "https://example.com/rss")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Story title")
        self.assertEqual(items[0].summary, "Short summary")
        self.assertEqual(items[0].url, "https://example.com/story")

    def test_parse_atom_entry(self) -> None:
        payload = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Atom story</title>
            <link href="https://example.com/atom-story" />
            <summary>Atom summary</summary>
            <updated>2026-07-02T12:00:00Z</updated>
          </entry>
        </feed>"""

        items = parse_feed(payload, "Atom", "curated_feed", "https://example.com/atom")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Atom story")
        self.assertEqual(items[0].summary, "Atom summary")


if __name__ == "__main__":
    unittest.main()

