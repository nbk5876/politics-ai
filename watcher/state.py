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
        self.data = {"seen": {}, "failures": {}, "alerted_sources": []}
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
