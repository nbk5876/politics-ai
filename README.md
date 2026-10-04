# Politics AI

A small AI Lab project that follows one news story. It watches a list of sources, notices new articles about the story, saves a copy, and sends a short note with the link.

**Status (2026-10-03):** version 0.1 of the watcher is written and tested. It runs only as a **dry run** for now. It does not send notifications, save articles or run on a schedule until the design is reviewed and approved for deployment. Design: [docs/design/politics-ai-watcher-v0.1.md](docs/design/politics-ai-watcher-v0.1.md).

## What it does
1. Reads each source in `config/sources.json` (RSS and Atom feeds in this version).
2. Keeps only items published since the story began (`since` in `config/rules.json`).
3. Matches the headline and summary against the story's phrases and words.
4. In a live run: saves the article text to `captured/`, sends a LabChan message and an email, and remembers the item so it is never reported twice.

5. Builds a shareable page, `ai-safety-topic-links.html`: headlines and links only, last 30 days, newest first. A dry run writes a local preview to `previews/` (not committed); uploading it to the web is a separate step that is not built or approved yet.

The watcher itself makes no model calls, so it costs nothing to run. Summaries by lcRachel are a separate step that is not wired up yet.

## Try it
Needs Python 3.10+ and nothing else (standard library only).

```
python -m watcher.run               # dry run: prints what would match, sends and saves nothing
python -m unittest discover -s tests
```

Other modes, once approved: `--baseline` (remember everything that exists now, report nothing) and `--live` (capture and notify).

## Layout
- `watcher/`: the code (`feeds.py` reads feeds, `rules.py` matches, `state.py` remembers, `capture.py` saves, `notify.py` sends)
- `config/`: `sources.json`, `rules.json`; `local.example.json` shows the local settings file (`local.json` stays out of git)
- `docs/design/`: the design; `docs/trials/`: notes from trying lcRachel on the accord text
- `tests/`: unit tests (no network needed)

## Not built yet
- Page-watching for sources without a feed (Anthropic news, Dario Amodei's essays)
- Automatic lcRachel summaries
- The twice-a-day scheduled run
- Email needs SMTP settings supplied through environment variables (see `watcher/notify.py`)
