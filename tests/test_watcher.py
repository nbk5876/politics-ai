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


# Tests that call runmod.main without --page/--state must never touch the real previews/ or state/ folders
# (an earlier run of the tests overwrote the preview page, and that file was then published by mistake).
_root_patch = None


def setUpModule():
    global _root_patch
    _root_patch = mock.patch.object(runmod, "ROOT", Path(tempfile.mkdtemp()))
    _root_patch.start()


def tearDownModule():
    _root_patch.stop()



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

    def test_nvidia_openshell_and_sentry_are_strong_phrases(self):
        import json as _json
        from pathlib import Path as _P
        rules = _json.loads((_P(__file__).resolve().parent.parent / "config" / "rules.json").read_text(encoding="utf-8"))
        src = {"id": "x", "label": "X"}
        for title in ("NVIDIA OpenShell launches today", "Nvidia Sentry explained", "Why NVIDIA SENTRY matters",
                      "NVIDIA Launches Open Agent Safety Platform"):
            self.assertTrue(matches({"title": title, "summary": ""}, src, rules)[0], title)
        self.assertFalse(matches({"title": "Open shell scripting tips", "summary": ""}, src, rules)[0])

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
        text, listed = format_digest(ms, 1)
        self.assertIn("t2", text)
        self.assertEqual(listed, 3)

    def test_digest_over_limit_says_how_many_are_not_listed(self):
        ms = [{"source": {"label": "S"}, "item": {"title": "x" * 100, "link": "https://e.com/" + "y" * 60}}
              for _ in range(30)]
        text, listed = format_digest(ms, 5, limit=1900)
        self.assertLess(listed, 30)
        self.assertLessEqual(len(text), 1900)
        self.assertIn(f"+{30 - listed} more not listed", text)


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


class ReviewFixTests(unittest.TestCase):
    """One test per finding in Debbie's review of 2026-10-03."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.src = [{"id": "atom", "label": "Atom", "type": "feed", "url": "u"}]
        (self.d / "s.json").write_text(json.dumps(self.src), encoding="utf-8")
        (self.d / "l.json").write_text(json.dumps({"labchan_dir": str(self.d)}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _feed(self, n, title="accord and AI safety news"):
        entries = "".join(
            f'<entry><id>tag:n:{i}</id><title>{title} {i}</title><link href="https://e.com/{i}"/></entry>'
            for i in range(n))
        return '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">' + entries + "</feed>"

    def _args(self, sources="s.json"):
        return ["--sources", str(self.d / sources), "--rules", str(self.d / "r.json"),
                "--local", str(self.d / "l.json"), "--state", str(self.d / "seen.json"),
                "--captured", str(self.d / "cap"), "--live"]

    def _run(self, feed, rules, lab):
        (self.d / "r.json").write_text(json.dumps(rules), encoding="utf-8")
        with mock.patch.object(runmod, "fetch", lambda url: (feed, url)), \
             mock.patch.object(runmod, "send_labchan", lab), \
             mock.patch.object(runmod, "send_email", return_value=False), \
             mock.patch.object(runmod, "capture", return_value=(self.d / "x.md", True)):
            return runmod.main(self._args())

    def test_1_failed_send_does_not_repeat_earlier_messages(self):
        rules = {**RULES, "notify_cap": 10}
        calls = []

        def flaky(text, local):
            calls.append(text)
            if len(calls) == 2:
                raise RuntimeError("discord down")

        with self.assertRaises(RuntimeError):
            self._run(self._feed(3), rules, flaky)
        seen = json.loads((self.d / "seen.json").read_text(encoding="utf-8"))["seen"]
        self.assertEqual(list(seen), ["tag:n:0"])  # saved despite the crash; item 1 only
        calls.clear()
        self._run(self._feed(3), rules, lambda text, local: calls.append(text))
        self.assertEqual(len(calls), 2)  # items 2 and 3 only, no repeat of item 1

    def test_1b_failure_counter_is_saved_when_a_send_crashes(self):
        (self.d / "s2.json").write_text(json.dumps(self.src + [
            {"id": "bad", "label": "Bad", "type": "feed", "url": "bad"}]), encoding="utf-8")
        (self.d / "r.json").write_text(json.dumps({**RULES, "notify_cap": 10}), encoding="utf-8")
        feed = self._feed(1)

        def fetch(url):
            if url == "bad":
                raise OSError("down")
            return feed, url

        def boom(text, local):
            raise RuntimeError("send failed")

        with mock.patch.object(runmod, "fetch", fetch), mock.patch.object(runmod, "send_labchan", boom), \
             mock.patch.object(runmod, "send_email", return_value=False), \
             mock.patch.object(runmod, "capture", return_value=(self.d / "x.md", True)):
            with self.assertRaises(RuntimeError):
                runmod.main(self._args("s2.json"))
        failures = json.loads((self.d / "seen.json").read_text(encoding="utf-8"))["failures"]
        self.assertEqual(failures, {"bad": 1})

    def test_2_whole_word_matching(self):
        src = {"id": "x", "label": "X"}
        according = {"title": "Chip regulation hearing", "summary": "According to officials, nothing changed."}
        rules = {**RULES, "weak": ["accord", "regulation"], "min_weak": 2}
        self.assertFalse(matches(according, src, rules)[0])  # 'According' is not the word 'accord'
        self.assertTrue(matches({"title": "The accord on regulation", "summary": ""}, src, rules)[0])
        prefix = {**RULES, "weak": ["collaborat*", "accord"], "min_weak": 2}
        self.assertTrue(matches({"title": "A collaboration accord", "summary": ""}, src, prefix)[0])

    def test_3_over_cap_items_not_in_digest_stay_unseen(self):
        rules = {**RULES, "notify_cap": 2}
        title = "accord and AI safety news " + "x" * 90
        calls = []
        self._run(self._feed(40, title=title), rules, lambda text, local: calls.append(text))
        self.assertEqual(len(calls), 3)  # 2 individual messages + 1 digest
        self.assertIn("more not listed", calls[-1])
        seen = json.loads((self.d / "seen.json").read_text(encoding="utf-8"))["seen"]
        self.assertLess(len(seen), 40)  # items without room in the digest are reported next run
        calls.clear()
        self._run(self._feed(40, title=title), rules, lambda text, local: calls.append(text))
        self.assertGreater(len(calls), 0)

    def test_4_title_only_hash_ignores_summary_changes(self):
        st = State(self.d / "st.json")
        a = {"id": "1", "title": "T", "summary": "first", "_title_only": True}
        st.mark(a)
        self.assertEqual(st.status({**a, "summary": "second"}), "seen")
        b = {"id": "2", "title": "T", "summary": "first"}
        st.mark(b)
        self.assertEqual(st.status({**b, "summary": "second"}), "updated")

    def test_5_email_failure_does_not_abort_or_undo_labchan_send(self):
        (self.d / "r.json").write_text(json.dumps({**RULES, "notify_cap": 10}), encoding="utf-8")
        calls = []
        with mock.patch.object(runmod, "fetch", lambda url: (self._feed(2), url)), \
             mock.patch.object(runmod, "send_labchan", lambda text, local: calls.append(text)), \
             mock.patch.object(runmod, "send_email", side_effect=OSError("smtp down")), \
             mock.patch.object(runmod, "capture", return_value=(self.d / "x.md", True)):
            runmod.main(self._args())
        self.assertEqual(len(calls), 2)
        seen = json.loads((self.d / "seen.json").read_text(encoding="utf-8"))["seen"]
        self.assertEqual(len(seen), 2)

    def test_6_leftover_temp_file_does_not_break_state(self):
        path = self.d / "seen.json"
        (self.d / "seen.json.tmp").write_text("{ half written", encoding="utf-8")
        st = State(path)  # no seen.json yet; the stray .tmp must be ignored
        st.mark({"id": "1", "title": "T", "summary": ""})
        st.save()
        self.assertEqual(State(path).status({"id": "1", "title": "T", "summary": ""}), "seen")
        self.assertFalse((self.d / "seen.json.tmp").exists())  # replaced into place

    def test_7_item_with_no_id_or_link_is_skipped(self):
        feed = "<rss><channel><item><title>accord and AI safety</title></item></channel></rss>"
        logs = []
        st = State(self.d / "st.json")
        with mock.patch.object(runmod, "fetch", lambda url: (feed, url)):
            found, _, new_items = runmod.collect(self.src, RULES, st, log=logs.append)
        self.assertEqual(found, [])
        self.assertEqual(new_items, [])
        self.assertTrue(any("no id and no link" in line for line in logs))


class PageTests(unittest.TestCase):
    NOW = None

    def setUp(self):
        from datetime import datetime, timezone
        self.now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

    def rec(self, i, title="Headline", link="https://example.com/a", published="2026-10-02T00:00:00Z", **kw):
        return {"id": f"id{i}", "title": title, "link": link, "source": "Src", "published": published,
                "reasons": "phrases: x", "first_seen": "2026-10-03T00:00:00+00:00", **kw}

    def test_newest_first_last_30_days_and_one_row_per_id(self):
        from watcher.page import select
        recs = [self.rec(1, published="2026-09-20T00:00:00Z"), self.rec(2, published="2026-10-02T00:00:00Z"),
                self.rec(3, published="2026-08-01T00:00:00Z"), self.rec(2, published="2026-10-02T00:00:00Z")]
        out = select(recs, self.now, days=30)
        self.assertEqual([r["id"] for r in out], ["id2", "id1"])  # id3 is older than 30 days, id2 once

    def test_titles_are_escaped_and_unsafe_links_are_not_linked(self):
        from watcher.page import render
        html = render([self.rec(1, title='<script>alert(1)</script> & "quotes"'),
                       self.rec(2, title="Bad link", link="javascript:alert(1)")], self.now)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("Bad link", html)  # the headline still shows, just not as a link

    def test_outbound_links_have_safe_rel_and_page_has_no_article_text_field(self):
        from watcher.page import render
        html = render([self.rec(1)], self.now)
        self.assertIn('rel="noopener noreferrer nofollow"', html)
        self.assertIn("headlines and links only", html)

    def test_empty_page_says_so(self):
        from watcher.page import render
        self.assertIn("No matches in this period yet.", render([], self.now))

    def test_dry_run_writes_only_the_preview_page_and_live_run_archives_what_it_sent(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            feed = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>a1</id>'
                    '<title>The White House Accord explained</title><link href="https://e.com/1"/>'
                    '<published>2026-10-03T08:00:00Z</published></entry></feed>')
            (d / "s.json").write_text(json.dumps([{"id": "s", "label": "S", "type": "feed", "url": "u"}]), encoding="utf-8")
            (d / "r.json").write_text(json.dumps({**RULES, "notify_cap": 5}), encoding="utf-8")
            (d / "l.json").write_text(json.dumps({"labchan_dir": str(d)}), encoding="utf-8")
            args = ["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--local", str(d / "l.json"),
                    "--state", str(d / "seen.json"), "--captured", str(d / "cap"), "--page", str(d / "out" / "p.html")]
            with mock.patch.object(runmod, "fetch", lambda url: (feed, url)), \
                 mock.patch.object(runmod, "send_labchan") as lab, \
                 mock.patch.object(runmod, "send_email", return_value=False), \
                 mock.patch.object(runmod, "capture", return_value=(d / "x.md", True)):
                runmod.main(args)  # dry run
                self.assertIn("White House Accord explained", (d / "out" / "p.html").read_text(encoding="utf-8"))
                lab.assert_not_called()
                self.assertFalse((d / "seen.json").exists())  # nothing remembered
                runmod.main(args + ["--live"])
            archive = json.loads((d / "seen.json").read_text(encoding="utf-8"))["archive"]
            self.assertEqual([r["id"] for r in archive], ["a1"])
            self.assertNotIn("summary", archive[0])


class SecondReviewTests(unittest.TestCase):
    """Findings from Debbie's re-check and her review of the links page (2026-10-03/04)."""

    @staticmethod
    def real_rules():
        return json.loads((Path(__file__).resolve().parent.parent / "config" / "rules.json").read_text(encoding="utf-8"))

    def test_generic_words_need_ai_context(self):
        rules, src = self.real_rules(), {"id": "x", "label": "X"}
        for title in ("Honda Accord recall tied to new regulation", "Frontier Airlines faces new regulation"):
            self.assertFalse(matches({"title": title, "summary": ""}, src, rules)[0], title)
        self.assertTrue(matches({"title": "White House weighs AI regulation", "summary": ""}, src, rules)[0])
        self.assertTrue(matches({"title": "NVIDIA OpenShell is out", "summary": ""}, src, rules)[0])  # strong: no context needed

    def test_third_round_loose_ends(self):
        rules, src = self.real_rules(), {"id": "x", "label": "X"}
        for title in ("Joint commitment to cut shipping emissions", "J'ai lu: Frontier regulation news"):
            self.assertFalse(matches({"title": title, "summary": ""}, src, rules)[0], title)
        self.assertTrue(matches({"title": "Joint Commitment on Frontier Responsibilities", "summary": ""}, src, rules)[0])

    def test_a_dot_i_dot_counts_as_ai_context(self):
        rules, src = self.real_rules(), {"id": "x", "label": "X"}
        for title in ("White House weighs A.I. regulation", "A.I. regulation: White House weighs in"):
            self.assertTrue(matches({"title": title, "summary": ""}, src, rules)[0], title)
        for title in ("White House weighs DA.I. regulation", "Honda Accord tied to new regulation"):
            self.assertFalse(matches({"title": title, "summary": ""}, src, rules)[0], title)

    def test_repeated_page_failures_alert_once_after_three_runs(self):
        with tempfile.TemporaryDirectory() as td:
            labs = []
            for _ in range(4):
                _, lab = self._live(td, self.FEED, [mock.patch.object(runmod, "render", side_effect=RuntimeError("x"))])
                labs.append(lab.call_args_list)
            alert_runs = [i for i, calls in enumerate(labs) if any("links page failed to build" in str(c) for c in calls)]
            self.assertEqual(alert_runs, [2])  # third failure in a row alerts, and only once
            failures = json.loads((Path(td) / "seen.json").read_text(encoding="utf-8"))["failures"]
            self.assertEqual(failures.get("page"), 4)

    def test_fetch_refuses_non_http_urls(self):
        from watcher.fetch import fetch
        for url in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"):
            with self.assertRaises(ValueError):
                fetch(url)

    def test_bing_host_must_match_exactly(self):
        from watcher.feeds import resolve_link
        real = "https%3a%2f%2fexample.com%2fa"
        for host in ("www.bing.com", "bing.com"):
            self.assertEqual(resolve_link(f"http://{host}/news/apiclick.aspx?url={real}"), "https://example.com/a")
        evil = f"http://evilbing.com/news/apiclick.aspx?url={real}"
        self.assertEqual(resolve_link(evil), evil)

    def test_future_date_cannot_pin_a_row_forever(self):
        from datetime import datetime, timedelta, timezone
        from watcher.page import select
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        rec = {"id": "f", "title": "T", "link": "https://e.com", "source": "S", "published": "2099-01-01T00:00:00Z",
               "reasons": "", "first_seen": "2026-10-03T00:00:00+00:00"}
        self.assertEqual(len(select([rec], now, days=30)), 1)
        self.assertEqual(len(select([rec], now + timedelta(days=40), days=30)), 0)  # expires like any other row

    def test_page_has_content_security_policy(self):
        from watcher.page import render
        self.assertIn("Content-Security-Policy", render([]))

    def test_archive_updates_title_and_prunes_old_records(self):
        from datetime import datetime, timedelta, timezone
        st = State(Path(tempfile.gettempdir()) / "politics-archive-test.json")
        st.data["archive"] = []
        old = {"id": "1", "title": "Old title", "reasons": "a", "first_seen": "2026-10-01T00:00:00+00:00"}
        st.archive(old)
        st.archive({**old, "title": "New title", "reasons": "b"})
        self.assertEqual([r["title"] for r in st.data["archive"]], ["New title"])
        st.prune_archive(datetime(2027, 1, 15, tzinfo=timezone.utc), days=90)
        self.assertEqual(st.data["archive"], [])

    def _live(self, td, feed, patches=()):
        d = Path(td)
        (d / "s.json").write_text(json.dumps([{"id": "s", "label": "S", "type": "feed", "url": "u"}]), encoding="utf-8")
        (d / "r.json").write_text(json.dumps({**RULES, "notify_cap": 5}), encoding="utf-8")
        (d / "l.json").write_text(json.dumps({"labchan_dir": str(d)}), encoding="utf-8")
        args = ["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--local", str(d / "l.json"),
                "--state", str(d / "seen.json"), "--captured", str(d / "cap"), "--page", str(d / "p.html"), "--live"]
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(runmod, "fetch", lambda url: (feed, url)))
            lab = stack.enter_context(mock.patch.object(runmod, "send_labchan"))
            stack.enter_context(mock.patch.object(runmod, "send_email", return_value=False))
            stack.enter_context(mock.patch.object(runmod, "capture", return_value=(d / "x.md", True)))
            for patch in patches:
                stack.enter_context(patch)
            runmod.main(args)
        return d, lab

    FEED = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>a1</id>'
            '<title>The White House Accord explained</title><link href="https://e.com/1"/>'
            '<published>2026-10-03T08:00:00Z</published></entry></feed>')

    def test_page_failure_does_not_lose_the_seen_store(self):
        with tempfile.TemporaryDirectory() as td:
            d, lab = self._live(td, self.FEED, [mock.patch.object(runmod, "render", side_effect=RuntimeError("render broke"))])
            self.assertEqual(lab.call_count, 1)
            seen = json.loads((d / "seen.json").read_text(encoding="utf-8"))["seen"]
            self.assertIn("a1", seen)  # sent item is remembered, so the next run will not re-send it

    def test_a_crash_between_archive_and_mark_repeats_rather_than_loses(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError):
                self._live(td, self.FEED, [mock.patch.object(State, "mark", side_effect=RuntimeError("killed"))])
            data = json.loads((Path(td) / "seen.json").read_text(encoding="utf-8"))
            self.assertEqual([r["id"] for r in data["archive"]], ["a1"])  # on the page
            self.assertNotIn("a1", data["seen"])  # not marked, so it is reported again, not lost


class AnalyticsTests(unittest.TestCase):
    MID = "G-TESTID1234"

    def test_id_is_validated(self):
        from watcher.page import valid_analytics_id
        self.assertEqual(valid_analytics_id(" " + self.MID + " "), self.MID)
        for bad in ("", None, "UA-12345-1", "g-lowercase1", "G-12", "G-ABC123'); alert(1);//", "G-ABC<script>"):
            self.assertIsNone(valid_analytics_id(bad), bad)

    def test_non_string_ids_and_odd_settings_files_do_not_crash(self):
        from watcher.page import valid_analytics_id, render
        for bad in (123, ["G-ABC123XYZ0"], {"a": 1}, True):
            self.assertIsNone(valid_analytics_id(bad), bad)
            self.assertNotIn("googletagmanager", render([], analytics_id=bad))
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "s.json").write_text("[]", encoding="utf-8")
            (d / "r.json").write_text(json.dumps(RULES), encoding="utf-8")
            for content in ("[1, 2]", '{"analytics_id": 123}', '{"analytics_id": ["x"]}', "not json"):
                (d / "l.json").write_text(content, encoding="utf-8")
                runmod.main(["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--state", str(d / "seen.json"),
                             "--local", str(d / "l.json"), "--page", str(d / "p.html")])
                self.assertNotIn("googletagmanager", (d / "p.html").read_text(encoding="utf-8"))

    def test_no_tag_and_strict_policy_when_not_configured(self):
        from watcher.page import render
        html = render([])
        self.assertNotIn("googletagmanager", html)
        self.assertNotIn("script-src", html)
        self.assertNotIn("Google Analytics", html)

    def test_invalid_id_adds_nothing_to_the_page(self):
        from watcher.page import render
        html = render([], analytics_id="G-ABC123'); alert(1);//")
        self.assertNotIn("alert(1)", html)
        self.assertNotIn("googletagmanager", html)

    def test_tag_notice_and_policy_when_configured(self):
        import base64, hashlib, re
        from watcher.page import render
        html = render([], analytics_id=self.MID)
        self.assertIn(f"https://www.googletagmanager.com/gtag/js?id={self.MID}", html)
        self.assertIn("This page uses Google Analytics to count visits.", html)
        inline = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode()
        csp = re.search(r'Content-Security-Policy" content="([^"]+)', html).group(1)
        self.assertIn(f"script-src 'sha256-{digest}' https://www.googletagmanager.com", csp)  # the inline script is allowed by hash
        self.assertNotIn("unsafe-inline'; script", csp)
        self.assertNotIn("script-src 'unsafe-inline'", csp)
        self.assertIn("default-src 'none'", csp)  # everything else is still blocked
        self.assertEqual(html.count("<script"), 2)  # the Google loader and the one start-up script, nothing else

    def test_run_passes_the_id_from_the_flag_to_the_page(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "s.json").write_text("[]", encoding="utf-8")
            (d / "r.json").write_text(json.dumps(RULES), encoding="utf-8")
            runmod.main(["--sources", str(d / "s.json"), "--rules", str(d / "r.json"), "--state", str(d / "seen.json"),
                         "--local", str(d / "none.json"), "--page", str(d / "p.html"), "--analytics-id", self.MID])
            self.assertIn(self.MID, (d / "p.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
