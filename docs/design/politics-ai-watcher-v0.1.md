# Politics AI watcher: design v0.1

Date: 2026-10-02
Author: Jeff (HPZ2Mini). Owner: TB.
Status: PROPOSED. Nothing is approved or built. Needs TB's explicit yes in the direct session, then Debbie's code review, before any build.

## 1. Purpose
TB wants to follow one story: a White House meeting on AI regulation, and an agreement among frontier model makers to work together on AI safety. If a named person (first example: Sam Altman) writes about it, the system should detect the article, save its text, and notify TB.

The story's facts (who attended, who signed, what the agreement says) are TB's account and are not verified by Jeff. The system must treat them as claims to confirm against primary sources, not as facts.

## 2. Scope
In scope: watch a list of sources, match new items against rules, save matches, summarize with citations, notify TB.
Out of scope for v0.1: publishing anything, sentiment or opinion output, social media scraping, any change to LabChan code, Rachel's code, or her model.

## 3. Why two parts
lcRachel only acts when a message reaches her and she has no search or schedule of her own. She also invents details when she has no source (2026-10-02 tests). So:
- Part 1, the **watcher** (a plain script on a schedule): no model calls, no token cost. It finds and saves.
- Part 2, the **summarizer** (lcRachel): runs only when the watcher has a match. She is given the saved text and told to cite and say "not found" when a source is silent.

## 4. Watcher design (PROPOSED)
1. **Sources list** (`sources.json`, edited by TB): each entry is a feed URL or page URL, plus a label.
   - Candidates, to be verified before use: Sam Altman's blog feed, the OpenAI blog feed, other participants' company blogs, a Google News RSS search for the story (the same mechanism Pulse uses for ad-hoc topics, last 24 hours), and the main outlets (AP, NPR, PBS, Politico, The Hill, ABC, CBS, Axios).
   - Not usable: X/Twitter posts (cannot be fetched), paywalled pages, outlets that block bots (Reuters).
2. **Match rule** (`rules.json`): an item matches when it is new AND (author or source is on the watch list) AND its title or text contains at least one story keyword (for example "safety agreement", "White House", "frontier"). Rules start loose and TB tightens them after the first week.
3. **Seen store** (`state/seen.json`): item URL and a hash of its text. An item is never reported twice; a changed article is reported once more, marked "updated".
4. **Capture**: on a match, fetch the page, extract the readable text, save it as `captured/<date>-<slug>.md` with the URL, fetch time and source label. The original text is kept untouched.
5. **Notify**: send TB a LabChan message with the title, source, URL and the saved filename. Option: email instead or as well (the lab already has a working SMTP script).
6. **Summarize** (optional switch, off by default): the watcher sends Rachel the saved file with the brief in section 5.
7. **Schedule**: a Windows Scheduled Task on HPZ2Mini, every N minutes (TB decides, see section 8). Runs, writes a one-line log, exits.

## 5. Rachel's brief for a match
- Use only the saved text. Cite the URL for every claim.
- Write 'not found' for anything the text does not say. Never guess a quote, date, number or name.
- Neutral. Attribute claims ("Altman wrote that ..."). Separate what the article states as fact from opinion.
- Under 1,500 characters, in this order: summary (3 to 5 sentences), key claims with where in the text, what the article does not say.
- Pinned facts P1 to P3 in `cc-jeff-politics-ai-draft-setup-20261002.md` carry these rules (TB pastes them).

## 6. Cost and limits
- Watcher: free to run. A few HTTP requests per source per run.
- Rachel: one model call per match. Her hourly ceiling is 20, so a burst of matches cannot overrun it; extra matches queue.
- Claude (Jeff, Debbie) are not woken by the watcher. No Monitor involved.

## 7. Failure modes and how each shows up
- Source down or blocking: logged; after 3 failed runs the watcher tells TB once.
- Page layout changes so text extraction fails: the capture is flagged "extraction failed" with the raw URL, never silently dropped.
- Too many matches (rules too loose): daily cap on notifications (default 10); the rest are listed in one digest message.
- Duplicate stories across outlets: grouped by title similarity in the digest; v0.1 only reports them side by side.
- Rachel invents: the summary is labeled "unchecked" until Jeff or Debbie spot-check two or three claims against the saved text.

## 8. Decisions needed from TB
1. Sources: which to watch first; confirm X/Twitter is not required.
2. People to watch: only Sam Altman, or also the other heads of the companies involved (TB names them).
3. Notify channel: LabChan to TB, email, or both.
4. Check frequency: for example every 30 minutes, hourly, or twice a day.
5. Where the saved articles live (suggest the repo's `captured/` folder, not tracked in git).
6. Whether Rachel summarizes automatically or only when TB asks.

## 9. Privacy
The articles are public. The watcher stores URLs and article text only. It does not store TB's personal details. Any page TB later publishes from this goes through the usual names-and-personal-details flag first.

## 10. Approval gate (the usual one)
Design doc (this), TB approval in the direct session, build, Debbie code review, TB deploy approval, live test. No step is skipped.

## 11. Test plan
1. Dry run: the watcher reads three sources and prints what would match; no notify, no save.
2. Seed run: it processes one known article and produces a capture file and a notification.
3. Dedup check: the same article is not reported twice.
4. Failure check: a dead source URL produces a log line, not a crash.
5. Rachel check: Jeff spot-checks her summary against the saved text and logs right, invented and not-found.

## 12. First manual step (no build needed)
TB has a URL for lcRachel. Run her once by hand on that article with the brief in section 5, and log what she does well and badly. That tells us how much the summarizer can be trusted before anything is automated.
