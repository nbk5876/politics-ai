"""Build the shareable web page of matches: headlines and links only, newest first.

Article text is never put on the page (it stays in captured/). Everything that comes from a
feed is HTML-escaped, and only http(s) links are allowed.
"""
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
  td.why { color: #555; font-size: .82rem; }
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


def _when(rec):
    return parse_date(rec.get("published", "")) or parse_date(rec.get("first_seen", ""))


def select(records, now, days=30):
    """Records from the last `days` days, newest first, one per id."""
    cutoff = now - timedelta(days=days)
    seen, out = set(), []
    for r in records:
        d = _when(r)
        if r["id"] in seen or (d is not None and d < cutoff):
            continue
        seen.add(r["id"])
        out.append((d or now, r))
    out.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in out]


def render(records, now=None, days=30):
    now = now or datetime.now(timezone.utc)
    rows = select(records, now, days)
    body = []
    for r in rows:
        d = _when(r)
        link = safe_url(r["link"])
        title = escape(r["title"] or r["link"])
        head = (f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer nofollow">{title}</a>'
                if link else title)
        body.append(f'<tr><td class="date">{d.strftime("%Y-%m-%d") if d else ""}</td><td>{head}</td>'
                    f'<td>{escape(r["source"])}</td><td class="why">{escape(r["reasons"])}</td></tr>')
    table = ('<div class="tablewrap"><table><thead><tr><th>Date</th><th>Headline</th><th>Source</th>'
             '<th>Matched on</th></tr></thead><tbody>\n' + "\n".join(body) + "\n</tbody></table></div>"
             if body else "<p>No matches in this period yet.</p>")
    stamp = now.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{TITLE}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<h1>{TITLE}</h1>
<div class="meta">{len(rows)} link(s) from the last {days} days, newest first. Updated {escape(stamp)}.</div>
<div class="note">Links to news and company posts about the White House Accord on Super Intelligence (September 29, 2026) and
related AI safety announcements. Found automatically by a small AI Lab project, <a href="{REPO}">Politics AI</a>:
headlines and links only, with the source named. A link here is not an endorsement, and the headlines are the
publishers' own words.</div>
{table}
<footer>Politics AI watcher, an AI Lab project. Source code and design: <a href="{REPO}">{REPO}</a></footer>
</div>
</body>
</html>
"""
