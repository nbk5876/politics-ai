"""Build the shareable web page of matches: headlines and links only, newest first.

Article text is never put on the page (it stays in captured/). Everything that comes from a
feed is HTML-escaped, and only http(s) links are allowed.
"""
import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from html import escape

from .rules import parse_date

TITLE = "AI Safety Topic Links"
REPO = "https://github.com/nbk5876/politics-ai"

CSS = """
  body { font-family: Arial, Helvetica, sans-serif; background: #f7f7f7; margin: 0;
         padding: 1rem; color: #222; line-height: 1.45; }
  .wrap { max-width: 64rem; margin: 0 auto; }
  h1 { margin: 0 0 .25rem; }
  .meta { color: #555; font-size: .9rem; margin-bottom: 1rem; }
  .note { background: #fff; border: 1px solid #ccc; padding: .6rem .8rem; font-size: .9rem; margin-bottom: 1rem; }
  .tablewrap { overflow-x: auto; background: #fff; border: 1px solid #ccc; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; vertical-align: top; font-size: .9rem; }
  th { background: #e9e9e9; }
  td.date { white-space: nowrap; }
  footer { margin-top: 1.5rem; color: #555; font-size: .85rem; }
  a { color: #0b57d0; }
"""


def safe_url(url):
    """Only plain http(s) links are allowed on the page."""
    u = (url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def record(m, now):
    """The archive record for one match (no article text)."""
    it = m["item"]
    return {"id": it["id"], "title": it["title"][:300], "link": it["link"], "source": m["source"]["label"],
            "published": it.get("published", ""), "reasons": "; ".join(m["reasons"]),
            "first_seen": now.isoformat(timespec="seconds")}


def _when(rec, now=None):
    """Published date, or first-seen date. A published date in the future is not believed: the row
    is dated by when we first saw it, so a bad date cannot pin it on top (or keep it) forever."""
    now = now or datetime.now(timezone.utc)
    pub, seen = parse_date(rec.get("published", "")), parse_date(rec.get("first_seen", ""))
    if pub is None:
        return seen
    if pub > now:
        return seen if seen is not None and seen <= now else now
    return pub


def select(records, now, days=30):
    """Records from the last `days` days, newest first, one per id."""
    cutoff = now - timedelta(days=days)
    seen, out = set(), []
    for r in records:
        d = _when(r, now)
        if r["id"] in seen or (d is not None and d < cutoff):
            continue
        seen.add(r["id"])
        out.append((d or now, r))
    out.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in out]


def valid_analytics_id(value):
    """A Google Analytics 4 measurement ID such as G-ABC123XYZ0, or None. Anything else is ignored,
    so a typo in the settings can never put odd text into the page."""
    if not isinstance(value, str):  # a number or list in the settings must not crash the run
        return None
    v = value.strip()
    return v if re.fullmatch(r"G-[A-Z0-9]{6,14}", v) else None


def analytics_parts(mid):
    """(head markup, content-security-policy) for Google Analytics, or ('', strict policy).

    The policy allows only Google's analytics hosts. The small inline start-up script is allowed by its
    hash, not by 'unsafe-inline', so no other inline script can run."""
    strict = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    if not mid:
        return "", strict
    inline = ("window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
              f"gtag('js',new Date());gtag('config','{mid}');")
    digest = base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode()
    csp = (strict + f"; script-src 'sha256-{digest}' https://www.googletagmanager.com"
           "; connect-src https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com"
           "; img-src https://*.google-analytics.com https://*.googletagmanager.com")
    markup = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>\n'
              f"<script>{inline}</script>")
    return markup, csp


def preview_tags(preview):
    """Link-preview meta tags (Open Graph and Twitter card) from a dict with page_url, image_url,
    description and optional image_alt. Returns '' unless every value is usable: https URLs, short text."""
    if not isinstance(preview, dict):
        return ""
    page_url, image_url = safe_url(preview.get("page_url")), safe_url(preview.get("image_url"))
    desc = preview.get("description")
    if not (page_url.startswith("https://") and image_url.startswith("https://") and isinstance(desc, str) and desc.strip()):
        return ""
    if re.search(r"\s", page_url) or re.search(r"\s", image_url):  # no spaces or newlines inside a URL
        return ""
    desc = " ".join(desc.split())[:200]
    alt = " ".join(str(preview.get("image_alt") or TITLE).split())[:120]
    q = lambda v: escape(v, quote=True)
    tags = [("name", "description", desc), ("property", "og:type", "website"), ("property", "og:site_name", "Politics AI"),
            ("property", "og:title", TITLE), ("property", "og:description", desc), ("property", "og:url", page_url),
            ("property", "og:image", image_url), ("property", "og:image:alt", alt),
            ("name", "twitter:card", "summary_large_image"), ("name", "twitter:title", TITLE),
            ("name", "twitter:description", desc), ("name", "twitter:image", image_url)]
    for key, name in (("image_width", "og:image:width"), ("image_height", "og:image:height")):
        v = preview.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and 0 < v < 10000:
            tags.append(("property", name, str(v)))
    return "\n".join(f'<meta {k}="{q(n)}" content="{q(v)}">' for k, n, v in tags)


def render(records, now=None, days=30, analytics_id=None, preview=None):
    now = now or datetime.now(timezone.utc)
    mid = valid_analytics_id(analytics_id)
    tag, csp = analytics_parts(mid)
    og = preview_tags(preview)
    rows = select(records, now, days)
    body = []
    for r in rows:
        d = _when(r, now)
        link = safe_url(r["link"])
        title = escape(r["title"] or r["link"])
        head = (f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer nofollow">{title}</a>'
                if link else title)
        body.append(f'<tr><td class="date">{d.strftime("%Y-%m-%d") if d else ""}</td><td>{head}</td>'
                    f'<td>{escape(r["source"])}</td></tr>')
    table = ('<div class="tablewrap"><table><thead><tr><th>Date</th><th>Headline</th><th>Source</th>'
             '</tr></thead><tbody>\n' + "\n".join(body) + "\n</tbody></table></div>"
             if body else "<p>No matches in this period yet.</p>")
    stamp = now.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>{TITLE}</title>
{og}
{tag}
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<h1>{TITLE}</h1>
<div class="meta">{len(rows)} link(s) from the last {days} days, newest first. Updated {escape(stamp)}.</div>
<div class="note">Links to news and company posts about the White House Accord on Super Intelligence (September 29, 2026) and
related AI safety announcements. Found automatically by a small AI Lab project, <a href="{REPO}">Politics AI</a>:
headlines and links only, with the source named.</div>
{table}
<footer>A link here is not an endorsement, and the headlines are the publishers' own words.<br>
Politics AI watcher, an AI Lab project. Source code and design: <a href="{REPO}">{REPO}</a></footer>
</div>
</body>
</html>
"""
