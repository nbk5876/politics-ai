# Politics AI

A small AI Lab project that follows one news story. It watches a list of sources, notices new articles about the story, saves a copy, sends a short note with the link, and keeps a public page of the links.

**Status (2026-10-03):** live. The watcher runs twice a day (8 AM and 8 PM), sends LabChan messages, saves articles locally, and publishes the links page: https://www.core3.com/politics-ai/ai-safety-topic-links.html

Design: [docs/design/politics-ai-watcher-v0.1.md](docs/design/politics-ai-watcher-v0.1.md)

## What it does
1. Reads each source in `config/sources.json`: RSS and Atom feeds, plus pages with no feed (the watcher finds the article links and opens the new ones).
2. Keeps only items published since the story began (`since` in `config/rules.json`).
3. Matches the headline and summary against the story's phrases and words.
4. In a live run: saves the article text to `captured/`, sends a LabChan message (and an email if SMTP settings are supplied), and remembers the item so it is never reported twice.
5. Builds `ai-safety-topic-links.html`: headlines and links only, last 30 days, newest first.
6. Uploads the page over SFTP (`watcher/publish.py`) when `publish` is set in `config/local.json`. The upload needs a pinned server host key and reads the password from the `DH_PASS` environment variable (handed to curl on stdin, never logged). The live page is then fetched and compared byte for byte.

The watcher itself makes no model calls, so it costs nothing to run. Summaries by lcRachel are a separate step that is not wired up yet.

## Try it
Needs Python 3.10+ and nothing else (standard library only).

```
python -m watcher.run                  # dry run: prints what would match, sends and saves nothing,
                                       # writes a local preview of the page to previews/
python -m unittest discover -s tests   # the tests (no network needed)
```

Other modes: `--baseline` (remember everything that exists now, report nothing), `--live` (capture, notify, publish), and `--cap N` (at most N individual messages, the rest in one digest).

## Running it on a schedule
`scripts/register-task.ps1` creates a Windows Scheduled Task, "PoliticsAI-Watcher", that runs `python -m watcher.run --live` at 8:00 AM and 8:00 PM. Output goes to `logs/watcher.log` (not committed).

## Layout
- `watcher/`: the code (`feeds.py` reads feeds, `rules.py` matches, `state.py` remembers, `capture.py` saves, `pages.py` watches pages with no feed, `notify.py` sends, `page.py` builds the page, `publish.py` uploads it)
- `config/`: `sources.json`, `rules.json`; `local.example.json` shows the local settings file (`local.json` stays out of git)
- `scripts/`: the scheduled-task setup
- `docs/design/`: the design; `docs/trials/`: notes from trying lcRachel on the accord text
- `tests/`: unit tests (no network needed)

## Not built yet
- Automatic lcRachel summaries
- Email needs SMTP settings supplied through environment variables (see `watcher/notify.py`)
- Grouping duplicate stories from different outlets
