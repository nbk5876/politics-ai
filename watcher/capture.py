"""Save a matched article to captured/ with its URL and fetch time."""
import re
from datetime import datetime
from pathlib import Path

from .extract import extract
from .fetch import fetch


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "item"


def capture(item, source, out_dir):
    """Fetch the article and save it. Returns (path, ok). Never raises."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = out_dir / f"{stamp}-{slug(source['id'])}-{slug(item['title'])}.md"
    try:
        html_text, final = fetch(item["link"])
        _, text = extract(html_text)
        ok = len(text) >= 600
        if ok:
            body = text
        elif text:
            body = ("(partial: short text, possibly a paywall or excerpt)\n\n" + text
                    + "\n\n" + item.get("summary", ""))
        else:
            body = "(extraction failed: no readable text found)\n\n" + item.get("summary", "")
    except Exception as e:  # network, HTTP, decoding
        final, ok = item["link"], False
        body = f"(extraction failed: {type(e).__name__}: {e})\n\n" + item.get("summary", "")
    head = (f"# {item['title']}\n\nSource: {source['label']}\nURL: {final}\n"
            f"Published: {item.get('published', '')}\n"
            f"Fetched: {datetime.now().isoformat(timespec='seconds')}\n\n---\n\n")
    path.write_text(head + body + "\n", encoding="utf-8")
    return path, ok
