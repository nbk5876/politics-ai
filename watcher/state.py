"""Seen-items store and failure counters (local JSON, never committed)."""
import hashlib
import json
import os
from pathlib import Path


def item_hash(item):
    """Hash of title and summary. Items flagged `_title_only` (sources whose summaries
    change as stories cluster) hash the title alone, so they are not re-reported."""
    raw = item.get("title", "")
    if not item.get("_title_only"):
        raw += "|" + item.get("summary", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"seen": {}, "failures": {}, "alerted_sources": [], "archive": []}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def status(self, item):
        """'new', 'updated' or 'seen'."""
        key = item["id"]
        if key not in self.data["seen"]:
            return "new"
        return "seen" if self.data["seen"][key] == item_hash(item) else "updated"

    def mark(self, item):
        self.data["seen"][item["id"]] = item_hash(item)

    def archive(self, rec):
        """Remember a notified match (headline, link, source, date: no article text) for the page.
        An 'updated' item replaces its older record, so the page shows the current headline."""
        for i, r in enumerate(self.data["archive"]):
            if r["id"] == rec["id"]:
                # a record that was adjacent and now matches central is promoted; central is never demoted
                tier = "central" if "central" in (r.get("tier", "central"), rec.get("tier", "central")) else "adjacent"
                self.data["archive"][i] = {**r, "title": rec["title"], "reasons": rec["reasons"], "tier": tier}
                return
        self.data["archive"].append(rec)

    def prune_archive(self, now, days=90):
        """Drop archive records first seen more than `days` days ago (the page only shows 30)."""
        from datetime import timedelta
        from .rules import parse_date
        keep = []
        for r in self.data["archive"]:
            d = parse_date(r.get("first_seen", ""))
            if d is None or d >= now - timedelta(days=days):
                keep.append(r)
        self.data["archive"] = keep

    def record_failure(self, source_id):
        n = self.data["failures"].get(source_id, 0) + 1
        self.data["failures"][source_id] = n
        return n

    def record_ok(self, source_id):
        self.data["failures"].pop(source_id, None)
        if source_id in self.data["alerted_sources"]:
            self.data["alerted_sources"].remove(source_id)

    def save(self):
        """Write to a temp file, then swap it in, so a crash cannot leave a half-written file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
