"""Watch ordinary web pages that have no feed (a news index or an essay list).

A page source (`"type": "page"` in config/sources.json) names an index page and a pattern for the links
that are articles, for example `^/news/[^/]+$`. Each run the watcher reads the index, takes the article
links, and treats every link it has not seen before as a new item: it opens the article to get the real
title, the published date (when the page states one) and the text, so the usual matching rules apply.

First run on a page: nothing is reported for old articles. Links with a date on or after `since` are
looked at; every other link is remembered silently, so the first run cannot flood anyone.
"""
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .extract import extract
from .fetch import fetch
from .rules import parse_date

MAX_NEW_PER_RUN = 15  # articles opened per source per run; the rest wait for the next run
DATE_AT_START = re.compile(r"^\s*([A-Z][a-z]{2,8})\.? (\d{1,2}),? (\d{4})\b")
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self._href, self._buf = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._buf = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+", " ", " ".join(self._buf)).strip()))
            self._href = None


def parse_links(html_text, page_url, pattern):
    """[(absolute_url, anchor_text)] for links on the same site whose path matches the pattern, in page order."""
    p = _Links()
    p.feed(html_text)
    rx, site, seen, out = re.compile(pattern), urlparse(page_url).netloc.replace("www.", ""), set(), []
    for href, text in p.links:
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = urljoin(page_url, href.split("#")[0].split("?")[0])
        u = urlparse(url)
        if u.scheme not in ("http", "https") or u.netloc.replace("www.", "") != site:
            continue
        if rx.search(u.path.rstrip("/") or "/") and url not in seen:
            seen.add(url)
            out.append((url, text))
    return out


def date_from_anchor(text):
    """'Oct 2, 2026 Announcements Title' -> datetime, or None."""
    m = DATE_AT_START.match(text or "")
    if m and m.group(1)[:3] in MONTHS:
        try:
            return datetime(int(m.group(3)), MONTHS[m.group(1)[:3]], int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def tidy_title(title, fallback=""):
    """Drop a trailing site name ('... \\ Anthropic', '... | Site') and a leading 'Dario Amodei —' byline."""
    t = unescape(title or "").replace("\xa0", " ")
    t = re.sub(r"\s*[\\|]\s*[^\\|]{0,40}$", "", t).strip()
    t = re.sub(r"^[A-Z][\w .]{0,30}\s[—–-]\s+", "", t).strip()
    return t or fallback


def published_from_html(html_text):
    """The published date a page states: an article:published_time meta tag (either attribute order) or a
    datePublished value in its structured data. Empty when the page gives none."""
    q = "[\"']"  # a single or double quote
    nq = "[^\"']+"  # anything up to the next quote
    for pattern in (rf"<meta[^>]+(?:property|name)={q}article:published_time{q}[^>]*content={q}({nq})",
                    rf"<meta[^>]+content={q}({nq}){q}[^>]*(?:property|name)={q}article:published_time",
                    rf"{q}datePublished{q}\s*:\s*{q}({nq})"):
        m = re.search(pattern, html_text)
        if m:
            return m.group(1)
    return ""


def read_page_items(src, state, since=None, fetcher=fetch, limit=MAX_NEW_PER_RUN):
    """Return (new article items, number of article links on the page). Each item has title, link, published,
    summary and text. The link count lets an empty or broken index page be noticed."""
    index_html, final = fetcher(src["url"])
    links = parse_links(index_html, final, src["link_pattern"])
    first_run = src["id"] not in state.data.setdefault("page_baselined", [])
    since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    items = []
    for url, text in links:
        if state.data["seen"].get(url):
            continue
        anchor_date = date_from_anchor(text)
        if first_run and not (anchor_date and since_dt and anchor_date >= since_dt):
            state.data["seen"][url] = "baseline"  # an old or undated link on the first run: remember, don't report
            continue
        if len(items) >= limit:
            break  # the rest are looked at next run
        title, body, published = tidy_title(text.split(" ", 3)[-1] if anchor_date else text, text), "", ""
        try:
            page_html, _ = fetcher(url)
            t, body = extract(page_html)
            title = tidy_title(t, title)
            published = published_from_html(page_html)
        except Exception:
            pass  # still reported from the index entry: title only
        if not published and anchor_date:
            published = anchor_date.isoformat()
        items.append({"id": url, "title": title[:300], "link": url, "published": published,
                      "summary": " ".join(body.split())[:400], "author": "", "publisher": "", "text": body})
    if src["id"] not in state.data["page_baselined"]:
        state.data["page_baselined"].append(src["id"])
    return items, len(links)
