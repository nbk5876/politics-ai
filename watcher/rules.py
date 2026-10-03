"""Decide whether a feed item matches the story."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_date(s):
    """Best-effort parse of an RSS or Atom date. Returns an aware datetime or None."""
    if not s:
        return None
    for fn in (lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")), parsedate_to_datetime):
        try:
            d = fn(s.strip())
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def matches(item, source, rules, text=""):
    """Return (matched, reasons). Loose on purpose; tighten config/rules.json later.

    - `since` (YYYY-MM-DD): items published before this date never match. Items whose date
      cannot be read are kept, so nothing is silently dropped.
    - `strong` phrases: any one is enough.
    - `weak` words: at least `min_weak` different ones are needed.
    - Sources that are not one named person's own feed set `require_keyword_in_title`, so the
      words must appear in the headline or summary, not only in the page body.
    """
    since = rules.get("since")
    if since:
        d = parse_date(item.get("published", ""))
        if d is not None and d < datetime.fromisoformat(since).replace(tzinfo=timezone.utc):
            return False, []
    head = " ".join([item.get("title", ""), item.get("summary", "")]).lower()
    hay = head if source.get("require_keyword_in_title") or not text else head + " " + text.lower()
    strong = [k for k in rules.get("strong", []) if k.lower() in hay]
    weak = [k for k in rules.get("weak", []) if k.lower() in hay]
    ok = bool(strong) or len(weak) >= rules.get("min_weak", 2)
    reasons = []
    if strong:
        reasons.append("phrases: " + ", ".join(strong[:3]))
    if weak:
        reasons.append("words: " + ", ".join(weak[:5]))
    if ok and source.get("people"):
        reasons.append("source person: " + ", ".join(source["people"]))
    return ok, reasons if ok else []
