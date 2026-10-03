"""Politics AI watcher: one run.

Default is a DRY RUN: it reads the sources and prints what would match. It sends nothing,
saves nothing and does not change the seen-store. Use --baseline once to mark everything
that exists now as seen, then --live for real runs (capture + notify).

    python -m watcher.run                 # dry run
    python -m watcher.run --baseline      # remember current items, report nothing
    python -m watcher.run --live          # capture, notify, update seen-store
"""
import argparse
import json
import sys
from pathlib import Path

from .capture import capture
from .feeds import parse_feed
from .fetch import fetch
from .notify import format_digest, format_match, send_email, send_labchan
from .rules import matches
from .state import State

ROOT = Path(__file__).resolve().parent.parent


def collect(sources, rules, state, baseline=False, log=print):
    """Read every enabled feed source. Returns (matches, failed_source_ids, new_items)."""
    found, failed, new_items = [], [], []
    for src in sources:
        if not src.get("enabled", True):
            continue
        if src.get("type") != "feed":
            log(f"skip {src['id']}: type '{src.get('type')}' is not supported yet")
            continue
        try:
            xml, _ = fetch(src["url"])
            items = parse_feed(xml)
        except Exception as e:
            n = state.record_failure(src["id"])
            failed.append(src["id"])
            log(f"FAIL {src['id']} ({n} in a row): {type(e).__name__}: {e}")
            continue
        state.record_ok(src["id"])
        count = 0
        for it in items:
            if not it["id"]:
                log(f"skip an item with no id and no link in {src['id']}: {it['title'][:60]!r}")
                continue
            it["_title_only"] = bool(src.get("hash_title_only"))
            status = state.status(it)
            if baseline:
                state.mark(it)
                continue
            if status == "seen":
                continue
            new_items.append(it)
            ok, reasons = matches(it, src, rules)
            if ok:
                found.append({"source": src, "item": it, "status": status, "reasons": reasons})
                count += 1
        log(f"ok   {src['id']}: {len(items)} items, {count} match" + (" (baseline: all marked seen)" if baseline else ""))
    return found, failed, new_items


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default=str(ROOT / "config" / "sources.json"))
    ap.add_argument("--rules", default=str(ROOT / "config" / "rules.json"))
    ap.add_argument("--local", default=str(ROOT / "config" / "local.json"))
    ap.add_argument("--state", default=str(ROOT / "state" / "seen.json"))
    ap.add_argument("--captured", default=str(ROOT / "captured"))
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args(argv)

    sources = json.loads(Path(a.sources).read_text(encoding="utf-8"))
    rules = json.loads(Path(a.rules).read_text(encoding="utf-8"))
    state = State(a.state)
    found, failed, new_items = collect(sources, rules, state, baseline=a.baseline)

    if a.baseline:
        state.save()
        print("baseline saved; nothing reported")
        return 0

    cap = rules.get("notify_cap", 10)
    print(f"\n{len(found)} match(es)" + ("" if a.live else " (dry run: nothing sent, saved or remembered)"))
    for m in found:
        print(f"- [{m['status']}] {m['item']['title']}\n    {m['source']['label']} | {m['item']['link']}\n    {'; '.join(m['reasons'])}")
    if not a.live:
        return 0

    local = json.loads(Path(a.local).read_text(encoding="utf-8"))
    found_ids = {m["item"]["id"] for m in found}
    for it in new_items:  # new but not matching: nothing to send, so remember them now
        if it["id"] not in found_ids:
            state.mark(it)
    email_warned = False

    def email(subject, body):
        """Email never aborts a run or undoes a LabChan send; a missing setup is said once."""
        nonlocal email_warned
        try:
            if not send_email(subject, body) and not email_warned:
                print("email not configured (POLITICS_SMTP_* variables); skipping email")
                email_warned = True
        except Exception as e:
            print(f"email failed: {type(e).__name__}: {e}")

    try:
        for m in found[:cap]:
            path, ok = capture(m["item"], m["source"], a.captured)
            text = format_match(m, path.name, ok)
            send_labchan(text, local)
            state.mark(m["item"])  # remembered right after its own send succeeded
            email(f"Politics AI: {m['item']['title']}", text)
        rest = found[cap:]
        if rest:
            digest, listed = format_digest(rest, cap)
            send_labchan(digest, local)
            for m in rest[:listed]:  # items the digest did not have room for stay unseen
                state.mark(m["item"])
            email("Politics AI: more matches", digest)
        for sid in failed:
            if state.data["failures"].get(sid, 0) >= 3 and sid not in state.data["alerted_sources"]:
                send_labchan(f"Politics AI: source '{sid}' has failed {state.data['failures'][sid]} runs in a row.", local)
                state.data["alerted_sources"].append(sid)
    finally:
        state.save()  # always: keeps what was sent and the failure counters, even after an error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
