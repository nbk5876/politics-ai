"""Tests for the adjacent tier (docs/design/adjacent-tier-proposal-v0.1.md). No network used."""
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from watcher import run as runmod
from watcher.page import record, render
from watcher.pages import read_page_items
from watcher.state import State

RULES = {
    "since": "2026-09-28",
    "strong": ["White House Accord"],
    "weak": ["accord"],
    "min_weak": 2,
    "notify_cap": 10,
    "adjacent": {
        "since": "2026-09-15",
        "strong": ["superintelligence"],
        "weak": ["treaty", "inspection*"],
        "min_weak": 2,
        "require_context": ["=AI", "superintelligence"],
    },
}
NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def feed(*entries):
    """entries: (id, title, published)"""
    body = "".join(
        f'<entry><id>{i}</id><title>{t}</title><link href="https://e.com/{i}"/><published>{p}</published></entry>'
        for i, t, p in entries)
    return '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">' + body + "</feed>"


CENTRAL_ITEM = ("c1", "White House Accord signed", "2026-10-03T08:00:00Z")
ADJ_ITEM = ("a1", "Senate bill would ban superintelligence", "2026-10-02T08:00:00Z")
OLD_ADJ_ITEM = ("a2", "Earlier superintelligence debate", "2026-09-20T08:00:00Z")
UNRELATED = ("u1", "Heating assistance for winter", "2026-10-02T08:00:00Z")


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = State(Path(self.tmp.name) / "seen.json")

    def run_collect(self, source_extra, *entries):
        src = [{"id": "s", "label": "S", "type": "feed", "url": "u", **source_extra}]
        with mock.patch.object(runmod, "fetch", lambda url: (feed(*entries), url)):
            return runmod.collect(src, RULES, self.state, log=lambda *_: None)[0]

    def test_adjacent_source_gives_adjacent_matches_and_central_stays_central(self):
        found = self.run_collect({"adjacent": True}, CENTRAL_ITEM, ADJ_ITEM, UNRELATED)
        tiers = {m["item"]["id"]: m["tier"] for m in found}
        self.assertEqual(tiers, {"c1": "central", "a1": "adjacent"})

    def test_loose_central_match_on_an_adjacent_source_is_adjacent_not_central(self):
        rules = {**RULES, "weak": ["accord", "AI safety"], "adjacent": {**RULES["adjacent"], "strong": [],
                                                                         "weak": ["nothing"]}}
        src = [{"id": "s", "label": "S", "type": "feed", "url": "u", "adjacent": True}]
        loose = ("l1", "Accord on AI safety praised", "2026-10-03T08:00:00Z")  # two central weak words, no strong phrase
        with mock.patch.object(runmod, "fetch", lambda url: (feed(loose), url)):
            adj_found = runmod.collect(src, rules, self.state, log=lambda *_: None)[0]
        self.assertEqual([m["tier"] for m in adj_found], ["adjacent"])
        self.assertTrue(adj_found[0]["reasons"][0].startswith("words:"))
        # the same item from a source that is not adjacent stays central, as before
        self.state = State(Path(self.tmp.name) / "seen2.json")
        plain = [{"id": "s", "label": "S", "type": "feed", "url": "u"}]
        with mock.patch.object(runmod, "fetch", lambda url: (feed(loose), url)):
            plain_found = runmod.collect(plain, rules, self.state, log=lambda *_: None)[0]
        self.assertEqual([m["tier"] for m in plain_found], ["central"])

    def test_a_source_not_marked_adjacent_never_produces_adjacent(self):
        found = self.run_collect({}, CENTRAL_ITEM, ADJ_ITEM)
        self.assertEqual([m["item"]["id"] for m in found], ["c1"])

    def test_adjacent_tier_has_its_own_earlier_start_date(self):
        found = self.run_collect({"adjacent": True}, OLD_ADJ_ITEM)
        self.assertEqual([m["tier"] for m in found], ["adjacent"])  # Sep 20: before central since, after adjacent since
        found2 = self.run_collect({"adjacent": True}, ("a3", "Old superintelligence post", "2026-09-01T00:00:00Z"))
        self.assertEqual(found2, [])  # before the adjacent since too

    def test_no_adjacent_block_means_no_adjacent_matches(self):
        src = [{"id": "s", "label": "S", "type": "feed", "url": "u", "adjacent": True}]
        rules = {k: v for k, v in RULES.items() if k != "adjacent"}
        with mock.patch.object(runmod, "fetch", lambda url: (feed(ADJ_ITEM), url)):
            found = runmod.collect(src, rules, self.state, log=lambda *_: None)[0]
        self.assertEqual(found, [])


class LiveRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        (self.d / "s.json").write_text(json.dumps(
            [{"id": "s", "label": "S", "type": "feed", "url": "u", "adjacent": True}]), encoding="utf-8")
        (self.d / "r.json").write_text(json.dumps(RULES), encoding="utf-8")
        (self.d / "l.json").write_text(json.dumps({"labchan_dir": str(self.d)}), encoding="utf-8")

    def run_live(self, *entries):
        lab = mock.Mock()
        cap = mock.Mock(return_value=(self.d / "x.md", True))
        mail = mock.Mock(return_value=False)
        with mock.patch.object(runmod, "fetch", lambda url: (feed(*entries), url)), \
             mock.patch.object(runmod, "send_labchan", lab), \
             mock.patch.object(runmod, "send_email", mail), \
             mock.patch.object(runmod, "capture", cap):
            runmod.main(["--sources", str(self.d / "s.json"), "--rules", str(self.d / "r.json"),
                         "--local", str(self.d / "l.json"), "--state", str(self.d / "seen.json"),
                         "--captured", str(self.d / "cap"), "--page", str(self.d / "p.html"), "--live"])
        return lab, cap, mail

    def test_adjacent_only_run_sends_nothing_but_is_archived_and_remembered(self):
        lab, cap, mail = self.run_live(ADJ_ITEM, UNRELATED)
        lab.assert_not_called(); cap.assert_not_called(); mail.assert_not_called()
        st = json.loads((self.d / "seen.json").read_text(encoding="utf-8"))
        self.assertEqual([(r["id"], r["tier"]) for r in st["archive"]], [("a1", "adjacent")])
        self.assertIn("a1", st["seen"])
        self.assertIn("Adjacent", (self.d / "p.html").read_text(encoding="utf-8"))
        lab2, _, _ = self.run_live(ADJ_ITEM, UNRELATED)  # the next run does not repeat it
        lab2.assert_not_called()
        st = json.loads((self.d / "seen.json").read_text(encoding="utf-8"))
        self.assertEqual(len(st["archive"]), 1)

    def test_central_item_still_alerts_and_adjacent_item_does_not(self):
        lab, cap, mail = self.run_live(CENTRAL_ITEM, ADJ_ITEM)
        self.assertEqual(lab.call_count, 1)
        self.assertIn("White House Accord signed", lab.call_args[0][0])
        self.assertNotIn("superintelligence", lab.call_args[0][0])
        self.assertEqual(cap.call_count, 1)  # only the central article is saved


class StateTests(unittest.TestCase):
    def test_adjacent_record_is_promoted_to_central_and_never_demoted(self):
        with tempfile.TemporaryDirectory() as td:
            st = State(Path(td) / "seen.json")
            base = {"id": "1", "title": "T", "link": "https://e.com/1", "source": "S", "published": "",
                    "reasons": "x", "first_seen": "2026-10-05T00:00:00+00:00"}
            st.archive({**base, "tier": "adjacent"})
            self.assertEqual(st.data["archive"][0]["tier"], "adjacent")
            st.archive({**base, "tier": "central"})
            self.assertEqual(st.data["archive"][0]["tier"], "central")
            st.archive({**base, "tier": "adjacent"})
            self.assertEqual(st.data["archive"][0]["tier"], "central")


def rec(i, tier=None, source="CNBC"):
    r = {"id": str(i), "title": f"Headline {i}", "link": f"https://example.com/{i}", "source": source,
         "published": "2026-10-04T00:00:00Z", "reasons": "", "first_seen": "2026-10-05T00:00:00+00:00"}
    if tier:
        r["tier"] = tier
    return r


class PageTests(unittest.TestCase):
    def test_record_carries_the_tier(self):
        m = {"source": {"label": "S"}, "item": {"id": "1", "title": "T", "link": "https://e.com", "published": ""},
             "reasons": ["x"], "tier": "adjacent"}
        self.assertEqual(record(m, NOW)["tier"], "adjacent")
        del m["tier"]
        self.assertEqual(record(m, NOW)["tier"], "central")

    def test_page_without_adjacent_links_has_no_column_and_no_switch(self):
        html = render([rec(1), rec(2, "central")], NOW, icons={})
        self.assertNotIn("<th>Topic</th>", html)
        self.assertNotIn('class="switch"', html)
        self.assertIn("2 link(s) from the last 30 days", html)

    def test_page_with_adjacent_links_has_topic_column_and_default_central_switch(self):
        html = render([rec(1), rec(2, "adjacent")], NOW, icons={})
        self.assertIn("<th>Topic</th>", html)
        self.assertIn('<input type="radio" name="show" id="show-central" checked>', html)
        self.assertIn('<input type="radio" name="show" id="show-all">', html)
        self.assertEqual(html.count('<tr class="adjacent">'), 1)
        self.assertIn("<td>Central</td>", html)
        self.assertIn("<td>Adjacent</td>", html)
        self.assertIn("1 central link(s) and 1 adjacent", html)
        self.assertIn("do not name the Accord itself", html)
        # the switch is CSS only: the rule hides adjacent rows while Central is selected
        self.assertIn("#show-central:checked ~ .tablewrap tr.adjacent { display: none; }", html)

    def test_switch_needs_no_script_and_no_policy_change(self):
        html = render([rec(1, "adjacent")], NOW, icons={})
        self.assertNotIn("<script", html)
        csp = re.search(r'Content-Security-Policy" content="([^"]+)', html).group(1)
        self.assertEqual(csp, "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; img-src data:")

    def test_hostile_text_in_adjacent_rows_is_still_escaped(self):
        html = render([rec(1, "adjacent", source="<script>alert(1)</script>")], NOW, icons={})
        self.assertNotIn("<script>alert(1)</script>", html)


class PageSourceFirstRunTests(unittest.TestCase):
    INDEX = '<a href="/media/in-the-news/ai-playbook">Exclusive: AI playbook</a><a href="/media/in-the-news/other">Other</a>'

    def fetcher(self, url):
        return (self.INDEX, url) if url.endswith("in-the-news") else ("<html><title>T</title><body>Body text.</body></html>", url)

    def run_page(self, **extra):
        with tempfile.TemporaryDirectory() as td:
            st = State(Path(td) / "seen.json")
            src = {"id": "k", "type": "page", "url": "https://khanna.house.gov/media/in-the-news",
                   "link_pattern": r"^/media/in-the-news/[^/]+$", **extra}
            items, listed = read_page_items(src, st, since="2026-09-15", fetcher=self.fetcher)
            return items, listed, st

    def test_default_first_run_remembers_undated_links_silently(self):
        items, listed, st = self.run_page()
        self.assertEqual((len(items), listed), (0, 2))

    def test_baseline_first_run_false_looks_at_the_links(self):
        items, listed, st = self.run_page(baseline_first_run=False)
        self.assertEqual((len(items), listed), (2, 2))
        self.assertIn("k", st.data["page_baselined"])


class ConfigTests(unittest.TestCase):
    def test_committed_config_is_valid_and_adjacent_sources_are_marked(self):
        root = Path(runmod.__file__).resolve().parent.parent / "config"
        rules = json.loads((root / "rules.json").read_text(encoding="utf-8"))
        sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
        self.assertIn("adjacent", rules)
        self.assertTrue(all(k in rules["adjacent"] for k in ("since", "strong", "weak", "min_weak", "require_context")))
        adj = {s["id"] for s in sources if s.get("adjacent")}
        self.assertEqual(adj, {"sanders-press", "khanna-in-the-news", "bing-news-adjacent"})


if __name__ == "__main__":
    unittest.main()
