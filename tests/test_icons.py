import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from watcher import icons
from watcher.page import render

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20
JPG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"x" * 20


def rec(i, source):
    return {"id": str(i), "title": f"T{i}", "link": f"https://example.com/{i}", "source": source,
            "published": "2026-10-04T00:00:00Z", "reasons": "", "first_seen": "2026-10-05T00:00:00+00:00"}


class IconFilesTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def test_outlet_drops_the_msn_aggregator(self):
        self.assertEqual(icons.outlet("Al Jazeera on MSN"), "Al Jazeera")
        self.assertEqual(icons.outlet("The Conversation"), "The Conversation")
        self.assertEqual(icons.outlet("Yahoo Finance"), "Yahoo Finance")

    def test_png_and_jpeg_become_data_uris_by_content_not_name(self):
        (self.d / "a.com.png").write_bytes(PNG)
        (self.d / "b.com.jpg").write_bytes(JPG)
        (self.d / "c.com.png").write_bytes(JPG)  # a JPEG saved under a .png name is still a JPEG
        self.assertTrue(icons.icon_uri("a.com", self.d).startswith("data:image/png;base64,"))
        self.assertTrue(icons.icon_uri("b.com", self.d).startswith("data:image/jpeg;base64,"))
        self.assertTrue(icons.icon_uri("c.com", self.d).startswith("data:image/jpeg;base64,"))

    def test_missing_oversized_or_wrong_type_files_give_no_icon(self):
        (self.d / "big.com.png").write_bytes(PNG + b"x" * icons.MAX_ICON_BYTES)
        (self.d / "html.com.png").write_bytes(b"<svg onload=alert(1)>")
        self.assertIsNone(icons.icon_uri("nothere.com", self.d))
        self.assertIsNone(icons.icon_uri("big.com", self.d))
        self.assertIsNone(icons.icon_uri("html.com", self.d))

    def test_map_ignores_bad_entries_and_a_missing_file(self):
        p = self.d / "m.json"
        p.write_text(json.dumps({"Good": "good.com", "Bad": "x\"onload=1", "Num": 5}), encoding="utf-8")
        self.assertEqual(icons.load_map(p), {"good": "good.com"})
        self.assertEqual(icons.load_map(self.d / "none.json"), {})
        p.write_text("not json", encoding="utf-8")
        self.assertEqual(icons.load_map(p), {})

    def test_the_committed_map_and_icon_files_match(self):
        names = icons.load_map()
        self.assertTrue(names)
        for name, domain in names.items():
            self.assertIsNotNone(icons.icon_uri(domain), f"no icon file for {name} ({domain})")


class PageIconTests(unittest.TestCase):
    ICONS = {"yahoo": "data:image/png;base64,AAAA", "al jazeera": "data:image/png;base64,BBBB"}

    def test_icon_rule_is_emitted_once_and_rows_use_the_class(self):
        html = render([rec(1, "Yahoo"), rec(2, "Yahoo")], NOW, icons=self.ICONS)
        self.assertEqual(html.count("url(data:image/png;base64,AAAA)"), 1)
        self.assertEqual(html.count('class="ico i0"'), 2)

    def test_aggregator_rows_use_the_outlet_icon(self):
        html = render([rec(1, "Al Jazeera on MSN")], NOW, icons=self.ICONS)
        self.assertIn('class="ico i0"', html)
        self.assertIn("<span>Al Jazeera on MSN</span>", html)

    def test_unknown_source_gets_a_letter_badge(self):
        html = render([rec(1, "Tech Times on MSN")], NOW, icons={})
        self.assertIn('class="ico badge" aria-hidden="true">T</span>', html)

    def test_hostile_source_name_is_escaped_in_name_and_badge(self):
        html = render([rec(1, "<b onload=1>")], NOW, icons={})
        self.assertNotIn("<b onload", html)
        self.assertIn("&lt;b onload=1&gt;", html)
        self.assertIn(">B</span>", html)

    def test_policy_allows_data_images_in_one_img_src_with_and_without_analytics(self):
        for mid in (None, "G-ABC123XYZ0"):
            html = render([], NOW, icons={}, analytics_id=mid)
            csp = re.search(r'Content-Security-Policy" content="([^"]+)', html).group(1)
            self.assertEqual(csp.count("img-src"), 1)
            self.assertIn("img-src data:", csp)
            self.assertIn("default-src 'none'", csp)
        self.assertIn("https://*.google-analytics.com", csp)

    def test_default_render_uses_the_committed_icons(self):
        html = render([rec(1, "CNBC")], NOW)
        self.assertIn("url(data:image/", html)


if __name__ == "__main__":
    unittest.main()
