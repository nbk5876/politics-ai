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
from datetime import datetime, timezone
from pathlib import Path

from .capture import capture
from .feeds import parse_feed
from .fetch import fetch
from .page import record, render, valid_analytics_id
from .notify import format_digest, format_match, send_email, send_labchan
from .publish import publish_page
from .pages import read_page_items
from .rules import matches
from .state import State

ROOT = Path(__file__).resolve().parent.parent


def collect(sources, rules, state, baseline=False, log=print):
    """Read every enabled feed source. Returns (matches, failed_source_ids, new_items)."""
    found, failed, new_items = [], [], []
    for src in sources:
        if not src.get("enabled", True):
            continue
        kind = src.get("type")
        if kind not in ("feed", "page"):
            log(f"skip {src['id']}: type '{kind}' is not supported")
            continue
        try:
            if kind == "feed":
                xml, _ = fetch(src["url"])
                items = parse_feed(xml)
                listed = len(items)
            else:
                items, listed = read_page_items(src, state, since=rules.get("since"), fetcher=fetch)
        except Exception as e:
            n = state.record_failure(src["id"])
            failed.append(src["id"])
            log(f"FAIL {src['id']} ({n} in a row): {type(e).__name__}: {e}")
            continue
        state.record_ok(src["id"])
        # A feed that comes back empty (or as a blank/error page) is not a failure on one run, but 3 in a row is
        # worth an alert; the counter lives next to the failure counters under "empty:<id>".
        if listed:
            state.record_ok("empty:" + src["id"])
        else:
            state.record_failure("empty:" + src["id"])
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
            ok, reasons = matches(it, src, rules, text=it.get("text", ""))
            if ok:
                found.append({"source": src, "item": it, "status": status, "reasons": reasons})
                count += 1
        log(f"ok   {src['id']}: {listed} {'items' if kind == 'feed' else 'links'}" + (f", {len(items)} new" if kind == "page" else "") + f", {count} match" + (" (baseline: all marked seen)" if baseline else ""))
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
    ap.add_argument("--page", default=str(ROOT / "previews" / "ai-safety-topic-links.html"),
                    help="where to write the shareable page (a local file; uploading is a separate, approved step)")
    ap.add_argument("--cap", type=int, default=None,
                    help="send at most this many individual messages; the rest go in one digest (default: notify_cap in rules.json)")
    ap.add_argument("--analytics-id", default=None,
                    help="Google Analytics 4 measurement ID for the page (default: analytics_id in config/local.json)")
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

    cap = a.cap if a.cap is not None else rules.get("notify_cap", 10)
    print(f"\n{len(found)} match(es)" + ("" if a.live else " (dry run: nothing sent, saved or remembered)"))
    for m in found:
        print(f"- [{m['status']}] {m['item']['title']}\n    {m['source']['label']} | {m['item']['link']}\n    {'; '.join(m['reasons'])}")
    now = datetime.now(timezone.utc)

    def analytics_id():
        mid = a.analytics_id
        if mid is None:  # the local settings file is optional in a dry run
            try:
                cfg = json.loads(Path(a.local).read_text(encoding="utf-8"))
                mid = cfg.get("analytics_id") if isinstance(cfg, dict) else None  # a non-object file counts as empty
            except (OSError, ValueError):
                mid = None
        if mid is not None and not valid_analytics_id(mid):
            print(f"ignoring analytics_id {str(mid)[:30]!r}: not a valid G- measurement ID")
        return mid

    def preview_settings():
        """Link-preview settings (page_url, image_url, description) from the optional local settings file."""
        try:
            cfg = json.loads(Path(a.local).read_text(encoding="utf-8"))
            return cfg.get("preview") if isinstance(cfg, dict) else None
        except (OSError, ValueError):
            return None

    def write_page(extra=()):
        recs = state.data["archive"] + [r for r in extra if all(r["id"] != x["id"] for x in state.data["archive"])]
        Path(a.page).parent.mkdir(parents=True, exist_ok=True)
        Path(a.page).write_text(render(recs, now, analytics_id=analytics_id(), preview=preview_settings()), encoding="utf-8")
        print(f"page written: {a.page}")

    if not a.live:
        write_page([record(m, now) for m in found])  # preview only: not remembered, not uploaded
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
            state.archive(record(m, now))  # archive first: a failure repeats an item rather than losing it
            state.mark(m["item"])  # remembered right after its own send succeeded
            email(f"Politics AI: {m['item']['title']}", text)
        rest = found[cap:]
        if rest:
            digest, listed = format_digest(rest, cap)
            send_labchan(digest, local)
            for m in rest[:listed]:  # items the digest did not have room for stay unseen
                state.archive(record(m, now))
                state.mark(m["item"])
            email("Politics AI: more matches", digest)
        for key, n in list(state.data["failures"].items()):
            if key.startswith("empty:") and n >= 3 and key not in state.data["alerted_sources"]:
                send_labchan(f"Politics AI: source '{key[6:]}' returned 0 items {n} runs in a row.", local)
                state.data["alerted_sources"].append(key)
        for sid in failed:
            if state.data["failures"].get(sid, 0) >= 3 and sid not in state.data["alerted_sources"]:
                send_labchan(f"Politics AI: source '{sid}' has failed {state.data['failures'][sid]} runs in a row.", local)
                state.data["alerted_sources"].append(sid)
    finally:
        try:
            state.prune_archive(now)
        except Exception as e:
            print(f"prune failed: {type(e).__name__}: {e}")
        state.save()  # first: what was sent must be remembered even if the page cannot be built
        def step(name, what, fn):
            """Run one housekeeping step. Failures are counted like a failed feed: the third in a
            row sends one LabChan alert, and a good run clears the count."""
            try:
                fn()
                state.record_ok(name)
                return True
            except Exception as e:
                n = state.record_failure(name)
                print(f"{what} ({n} in a row): {type(e).__name__}: {e}")
                if n >= 3 and name not in state.data["alerted_sources"]:
                    try:
                        send_labchan(f"Politics AI: {what} {n} runs in a row.", local)
                        state.data["alerted_sources"].append(name)
                    except Exception as e2:
                        print(f"alert failed: {type(e2).__name__}: {e2}")
                return False

        built = step("page", "the links page failed to build", write_page)
        if built and local.get("publish"):
            step("publish", "the links page upload failed", lambda: publish_page(a.page, local["publish"]))
        state.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
