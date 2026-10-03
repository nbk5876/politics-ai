"""Tests for the watcher. Run: python -m unittest discover -s tests -v   (no network used)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from watcher import run as runmod
from watcher.extract import extract
from watcher.feeds import parse_feed
from watcher.notify import LABCHAN_LIMIT, format_digest, format_match
from watcher.rules import matches
from watcher.state import State

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry><id>tag:a:1</id><title>Working together on AI safety</title>
  <link rel="alternate" href="https://example.com/1"/><published>2026-10-03T08:00:00Z</published>
  <content type="html">&lt;p&gt;We agreed to collaborate on the accord.&lt;/p&gt;</content></entry>
 <entry><id>tag:a:2</id><title>My favorite books</title>
  <link rel="alternate" href="https://example.com/2"/><summary>Reading list.</summary></entry>
</feed>"""

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
 <item><title>Frontier labs sign accord</title><link>https://example.com/r1</link>
  <guid>r1</guid><pubDate>Fri, 03 Oct 2026 10:00:00 GMT</pubDate>
  <description>&lt;b&gt;Companies&lt;/b&gt; commit to controls.</description><dc:creator>A Reporter</dc:creator></item>
</channel></rss>"""

RULES = {"strong": ["White House Accord"], "weak": ["accord", "AI safety", "collaborat"], "min_weak": 2, "notify_cap": 2}


class FeedTests(unittest.TestCase):
    def test_parse_atom(self):
        items = parse_feed(ATOM)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["link"], "https://example.com/1")
        self.assertIn("collaborate", items[0]["summary"])
        self.assertNotIn("<p>", items[0]["summary"])

    def test_parse_rss(self):
        (it,) = parse_feed(RSS)
        self.assertEqual(it["id"], "r1")
        self.assertEqual(it["author"], "A Reporter")
        self.assertEqual(it["summary"], "Companies commit to controls.")


class ResolveTests(unittest.TestCase):
    def test_bing_redirect_is_unwrapped_and_used_as_stable_id(self):
        feed = ("<rss><channel><item><title>T</title><link>http://www.bing.com/news/apiclick.aspx?ref=x&amp;tid=ABC"
                "&amp;url=https%3a%2f%2fexample.com%2fa%2fb&amp;c=1</link></item></channel></rss>")
        (it,) = parse_feed(feed)
        self.assertEqual(it["link"], "https://example.com/a/b")
        self.assertEqual(it["id"], "https://example.com/a/b")

    def test_other_links_are_left_alone(self):
        from watcher.feeds import resolve_link
        self.assertEqual(resolve_link("https://news.google.com/rss/articles/xyz"), "https://news.google.com/rss/articles/xyz")


class RuleTests(unittest.TestCase):
    def test_keyword_match_and_miss(self):
        a, b = parse_feed(ATOM)
        src = {"id": "x", "label": "X", "people": ["Someone"]}
        self.assertTrue(matches(a, src, RULES)[0])
        self.assertFalse(matches(b, src, RULES)[0])

    def test_title_only_sources_ignore_body_text(self):
        (it,) = parse_feed(RSS.replace("accord", "story").replace("controls", "stuff"))
        body = "the accord and AI safety are mentioned deep in the body"
        src = {"id": "x", "label": "X", "require_keyword_in_title": True}
        self.assertFalse(matches(it, src, RULES, text=body)[0])
        self.assertTrue(matches(it, {"id": "x", "label": "X"}, RULES, text=body)[0])

    def test_one_weak_word_is_not_enough_but_strong_phrase_is(self):
        src = {"id": "x", "label": "X"}
        self.assertTrue(matches({"title": "Our AI safety accord", "summary": ""}, src, RULES)[0])  # two weak words
        self.assertFalse(matches({"title": "A new accord", "summary": ""}, src, RULES)[0])
        self.assertTrue(matches({"title": "The White House Accord explained", "summary": ""}, src, RULES)[0])

    def test_since_date_drops_old_items_but_keeps_unreadable_dates(self):
        src = {"id": "x", "label": "X"}
        rules = {**RULES, "since": "2026-09-29"}
        old = {"title": "The White House Accord", "summary": "", "published": "2026-09-01T00:00:00Z"}
        new = {**old, "published": "Fri, 03 Oct 2026 10:00:00 GMT"}
        odd = {**old, "published": "sometime last week"}
        self.assertFalse(matches(old, src, rules)[0])
        self.assertTrue(matches(new, src, rules)[0])
        self.assertTrue(matches(odd, src, rules)[0])


class StateTests(unittest.TestCase):
    def test_new_seen_updated_and_save(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "seen.json"
            st = State(path)
            it = {"id": "1", "title": "T", "summary": "S"}
            self.assertEqual(st.status(it), "new")
            st.mark(it)
            st.save()
            st2 = State(path)
            self.assertEqual(st2.status(it), "seen")
            self.assertEqual(st2.status({**it, "summary": "changed"}), "updated")

    def test_failure_counter_resets(self):
        st = State(Path(tempfile.gettempdir()) / "nonexistent-politics-state.json")
        self.assertEqual(st.record_failure("s"), 1)
        self.assertEqual(st.record_failure("s"), 2)
        st.record_ok("s")
        self.assertEqual(st.record_failure("s"), 1)


class ExtractTests(unittest.TestCase):
    def test_prefers_article_and_skips_nav(self):
        para = "This is a real paragraph of article text. " * 8
        html = f"<html><title>T</title><nav><p>menu menu</p></nav><article><p>{para}</p></article></html>"
        title, text = extract(html)
        self.assertEqual(title, "T")
        self.assertIn("real paragraph", text)
        self.assertNotIn("menu", text)


class NotifyTests(unittest.TestCase):
    def test_message_is_short_and_line_broken(self):
        m = {"source": {"label": "Src"}, "item": {"title": "T" * 3000, "link": "https://e.com", "published": ""},
             "status": "new", "reasons": ["keywords: accord"]}
        text = format_match(m, "file.md")
        self.assertLessEqual(len(text), LABCHAN_LIMIT)
        self.assertGreater(text.count("\n"), 5)

    def test_digest_lists_titles(self):
        ms = [{"source": {"label": "S"}, "item": {"title": f"t{i}", "link": "u"}} for i in range(3)]
        self.assertIn("t2", format_digest(ms, 1))


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.tmp.name) / "seen.json")
        self.sources = [
            {"id": "atom", "label": "Atom", "type": "feed", "url": "u1", "people": ["P"]},
            {"id": "rss", "label": "RSS", "type": "feed", "url": "u2"},
            {"id": "page", "label": "Page", "type": "page", "url": "u3"},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_fetch(self, url):
        if url == "u2":
            raise OSError("boom")
        return (ATOM, url)

    def test_dry_run_matches_skips_pages_and_survives_failure(self):
        with mock.patch.object(runmod, "fetch", self._fake_fetch):
            found, failed, new_items = runmod.collect(self.sources, RULES, self.state, log=lambda *_: None)
        self.assertEqual([m["item"]["id"] for m in found], ["tag:a:1"])
        self.assertEqual(failed, ["rss"])
        self.assertEqual(len(new_items), 2)
        self.assertEqual(self.state.data["failures"]["rss"], 1)

    def test_baseline_marks_everything_and_reports_nothing(self):
        with mock.patch.object(runmod, "fetch", self._fake_fetch):
            found, _, _ = runmod.collect(self.sources, RULES, self.state, baseline=True, log=lambda *_: None)
            self.assertEqual(found, [])
            found, _, _ = runmod.collect(self.sources, RULES, self.state, log=lambda *_: None)
        self.assertEqual(found, [])

    def test_dry_run_main_sends_and_saves_nothing(self):
        d = Path(self.tmp.name)
        (d / "s.json").write_text(json.dumps(self.sources[:1]), encoding="utf-8")
        (d / "r.json").write_text(json.dumps(RULES), encoding="utf-8")
        with mock.patch.object(runmod, "fetch", self._fake_fetch), \
             mock.patch.object(runmod, "send_labchan") as lab, \
             mock.patch.object(runmod, "send_email") as mail, \
             mock.patch.object(runmod, "capture") as cap:
            runmod.main(["--sources", str(d / "s.json"), "--rules", str(d / "r.json"),
                         "--state", str(d / "seen.json"), "--captured", str(d / "cap")])
        lab.assert_not_called(); mail.assert_not_called(); cap.assert_not_called()
        self.assertFalse((d / "seen.json").exists())

    def test_live_run_notifies_marks_seen_and_respects_cap(self):
        d = Path(self.tmp.name)
        many = ATOM.replace("</feed>", "".join(
            f'<entry><id>tag:a:x{i}</id><title>accord and AI safety news {i}</title><link href="https://e.com/{i}"/></entry>'
            for i in range(4)) + "</feed>")
        (d / "s.json").write_text(json.dumps(self.sources[:1]), encoding="utf-8")
        (d / "r.json").write_text(json.dumps(RULES), encoding="utf-8")
        (d / "l.json").write_text(json.dumps({"labchan_dir": str(d)}), encoding="utf-8")
        with mock.patch.object(runmod, "fetch", lambda url: (many, url)), \
             mock.patch.object(runmod, "send_labchan") as lab, \
             mock.patch.object(runmod, "send_email", return_value=False), \
             mock.patch.object(runmod, "capture", return_value=(d / "x.md", True)):
            runmod.main(["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--local", str(d / "l.json"),
                         "--state", str(d / "seen.json"), "--captured", str(d / "cap"), "--live"])
            # 5 matches, cap 2 -> 2 individual messages + 1 digest
            self.assertEqual(lab.call_count, 3)
            lab.reset_mock()
            runmod.main(["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--local", str(d / "l.json"),
                         "--state", str(d / "seen.json"), "--captured", str(d / "cap"), "--live"])
            lab.assert_not_called()  # second run: everything already seen


if __name__ == "__main__":
    unittest.main()
