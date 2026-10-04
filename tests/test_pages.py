"""Tests for page-watching (sources with no feed). No network: the fetcher is replaced by a fake."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from watcher import run as runmod
from watcher.pages import date_from_anchor, parse_links, read_page_items, tidy_title
from watcher.state import State

INDEX = """<html><body><nav><a href="/news">All news</a></nav>
<a href="/news/new-post">Oct 2, 2026 Announcements Anthropic invests in agent safety</a>
<a href="/news/recent-post">Sep 25, 2026 Policy A recent policy post</a>
<a href="/news/old-post">Aug 1, 2026 Announcements An old post</a>
<a href="/news/new-post">duplicate link</a>
<a href="https://evil.example.com/news/x">Oct 2, 2026 Elsewhere</a>
<a href="javascript:alert(1)">bad</a><a href="/careers">Careers</a>
<a href="https://www.anthropic.com/news/absolute-link?utm=1#frag">Sep 26, 2026 News An absolute link</a>
</body></html>"""

ARTICLE = ("<html><head><title>{t} \\ Anthropic</title><meta property=\"article:published_time\" content=\"{d}\"></head>"
           "<body><article><p>{body}</p></article></body></html>")
SRC = {"id": "anthropic", "label": "Anthropic news", "type": "page", "url": "https://www.anthropic.com/news",
       "link_pattern": "^/news/[^/]+$", "require_keyword_in_title": True}
RULES = {"strong": [], "weak": ["agent*", "safety"], "min_weak": 2, "require_context": ["=AI"],
         "since": "2026-09-24", "notify_cap": 5}


def fake_fetcher(pages):
    def fetcher(url):
        if url not in pages:
            raise OSError("404 " + url)
        return pages[url], url
    return fetcher


class LinkTests(unittest.TestCase):
    def test_only_matching_same_site_http_links_are_taken_once_in_page_order(self):
        links = parse_links(INDEX, "https://www.anthropic.com/news", "^/news/[^/]+$")
        self.assertEqual([u for u, _ in links], [
            "https://www.anthropic.com/news/new-post", "https://www.anthropic.com/news/recent-post",
            "https://www.anthropic.com/news/old-post", "https://www.anthropic.com/news/absolute-link"])

    def test_date_at_the_start_of_the_anchor_text(self):
        d = date_from_anchor("Oct 2, 2026 Announcements Anthropic invests")
        self.assertEqual((d.year, d.month, d.day), (2026, 10, 2))
        self.assertIsNone(date_from_anchor("Anthropic invests Oct 2, 2026"))
        self.assertIsNone(date_from_anchor("Xyz 2, 2026 nope"))
        self.assertIsNone(date_from_anchor("Feb 31, 2026 impossible date"))

    def test_titles_lose_the_site_suffix_and_byline(self):
        self.assertEqual(tidy_title("Claude Frontier Academy: $100M \\ Anthropic"), "Claude Frontier Academy: $100M")
        self.assertEqual(tidy_title("Dario Amodei —\xa0We Must Pace the Frontier"), "We Must Pace the Frontier")
        self.assertEqual(tidy_title("", "fallback"), "fallback")


class ReadPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.tmp.name) / "seen.json")
        self.pages = {
            "https://www.anthropic.com/news": INDEX,
            "https://www.anthropic.com/news/new-post": ARTICLE.format(
                t="Anthropic invests in agent safety", d="2026-10-02T23:01:00.000Z", body="Body text about agents."),
            "https://www.anthropic.com/news/recent-post": ARTICLE.format(
                t="A recent policy post", d="2026-09-25T10:00:00Z", body="Policy body."),
            "https://www.anthropic.com/news/absolute-link": ARTICLE.format(
                t="An absolute link", d="2026-09-26T10:00:00Z", body="Other."),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_reports_only_recent_dated_links_and_remembers_the_rest_silently(self):
        items, listed = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fake_fetcher(self.pages))
        self.assertEqual(listed, 4)
        self.assertEqual(sorted(i["title"] for i in items),
                         ["A recent policy post", "An absolute link", "Anthropic invests in agent safety"])
        self.assertEqual(self.state.data["seen"]["https://www.anthropic.com/news/old-post"], "baseline")
        first = next(i for i in items if "invests" in i["title"])
        self.assertEqual(first["published"], "2026-10-02T23:01:00.000Z")
        self.assertIn("agents", first["summary"])
        self.assertIn("anthropic", self.state.data["page_baselined"])

    def test_undated_page_is_fully_baselined_on_the_first_run(self):
        src = {"id": "essays", "label": "Essays", "type": "page", "url": "https://x.org/",
               "link_pattern": "^/(essay|post)/[^/]+$"}
        index = '<a href="/essay/old-essay">Old essay</a><a href="/post/older-post">Older post</a>'
        items, listed = read_page_items(src, self.state, since="2026-09-24", fetcher=fake_fetcher({"https://x.org/": index}))
        self.assertEqual((items, listed), ([], 2))
        # a new post appears later: only that one is reported, read from its article page
        pages = {"https://x.org/": index + '<a href="/post/brand-new">Brand new</a>',
                 "https://x.org/post/brand-new": "<html><title>Dario Amodei —\xa0Brand New</title><body><p>Text.</p></body></html>"}
        items, listed = read_page_items(src, self.state, since="2026-09-24", fetcher=fake_fetcher(pages))
        self.assertEqual([i["title"] for i in items], ["Brand New"])
        self.assertEqual(items[0]["published"], "")  # no date on the page: shown by first-seen date

    def test_second_run_reports_only_links_not_seen_before(self):
        fetcher = fake_fetcher(self.pages)
        items, _ = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fetcher)
        for it in items:
            self.state.mark(it)
        items, _ = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fetcher)
        self.assertEqual(items, [])

    def test_an_unreadable_article_is_still_reported_from_the_index_entry(self):
        pages = {k: v for k, v in self.pages.items() if not k.endswith("new-post")}
        items, _ = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fake_fetcher(pages))
        new = next(i for i in items if i["link"].endswith("/news/new-post"))
        self.assertEqual(new["title"], "Announcements Anthropic invests in agent safety")  # index text, date removed
        self.assertTrue(new["published"].startswith("2026-10-02"))

    def test_at_most_limit_articles_are_opened_per_run_and_the_rest_wait(self):
        index = "".join(f'<a href="/news/p{i}">Oct {i}, 2026 News Post {i}</a>' for i in range(1, 8))
        pages = {"https://www.anthropic.com/news": index}
        pages.update({f"https://www.anthropic.com/news/p{i}":
                      ARTICLE.format(t=f"Post {i}", d="2026-10-03T00:00:00Z", body="x") for i in range(1, 8)})
        first, _ = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fake_fetcher(pages), limit=3)
        self.assertEqual(len(first), 3)
        for it in first:
            self.state.mark(it)
        second, _ = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fake_fetcher(pages), limit=3)
        self.assertEqual(len(second), 3)
        self.assertTrue({i["id"] for i in first}.isdisjoint({i["id"] for i in second}))  # none repeated

    def test_a_broken_index_page_has_zero_links(self):
        pages = {SRC["url"]: "<html>Service unavailable</html>"}
        items, listed = read_page_items(SRC, self.state, since="2026-09-24", fetcher=fake_fetcher(pages))
        self.assertEqual((items, listed), ([], 0))


class CollectWithPagesTests(unittest.TestCase):
    def _collect(self, state, pages):
        fetcher = fake_fetcher(pages)
        with mock.patch.object(runmod, "read_page_items",
                               lambda s, st, since=None, fetcher=None: read_page_items(s, st, since=since, fetcher=fake_fetcher(pages))):
            return runmod.collect([SRC], RULES, state, log=lambda *_: None)

    def test_collect_matches_page_items_on_title_and_summary(self):
        with tempfile.TemporaryDirectory() as td:
            state = State(Path(td) / "seen.json")
            pages = {SRC["url"]: '<a href="/news/a">Oct 2, 2026 News AI agent safety update</a>',
                     "https://www.anthropic.com/news/a": ARTICLE.format(
                         t="AI agent safety update", d="2026-10-02T00:00:00Z", body="Details.")}
            found, failed, _ = self._collect(state, pages)
            self.assertEqual(failed, [])
            self.assertEqual([m["item"]["title"] for m in found], ["AI agent safety update"])

    def test_a_blank_index_counts_toward_the_empty_alert_and_a_quiet_day_does_not(self):
        with tempfile.TemporaryDirectory() as td:
            state = State(Path(td) / "seen.json")
            pages = {SRC["url"]: '<a href="/news/a">Oct 1, 2026 News Quiet</a>',
                     "https://www.anthropic.com/news/a": ARTICLE.format(t="Quiet", d="2026-10-01T00:00:00Z", body="x")}
            _, _, new_items = self._collect(state, pages)
            for it in new_items:
                state.mark(it)
            self._collect(state, pages)  # nothing new, but the page still lists a link
            self.assertNotIn("empty:anthropic", state.data["failures"])
            self._collect(state, {SRC["url"]: "<html>blank</html>"})
            self.assertEqual(state.data["failures"]["empty:anthropic"], 1)


if __name__ == "__main__":
    unittest.main()
