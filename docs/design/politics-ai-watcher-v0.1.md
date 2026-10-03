# Politics AI watcher: design v0.1

**Date:** 2026-10-02  
**Status:** Design agreed, waiting for approval to build. Nothing is built yet.  
**Written by:** Jeff

<img src="images/welcome-splash.png" alt="The team: lcRachel (ChatGPT Cloud), Jeff and Debbie (AI Lab)" width="50%">

*The AI Lab team. lcRachel summarizes, Jeff designs and builds, Debbie reviews.*

## 1. Purpose

**In plain English:** Politics AI is a small AI Lab project that follows one news story so nobody has to keep checking for updates. It watches a list of websites, notices when something new appears about the story, saves a copy, and sends a short summary with links.

**The story we are starting with:** a joint commitment on AI safety, titled the "White House Accord on Super Intelligence", dated September 29, 2026. Its signature block lists the President and the leaders of several major AI companies. The full text is summarized in section 1a.

**Who we will watch first:** Sam Altman (OpenAI) and Dario Amodei (Anthropic). Both write publicly and often. The watcher looks for new posts by them that touch the story, such as AI safety, the accord, or working together across companies. Amodei is listed in the accord's signature block; OpenAI's entry there is Greg Brockman, so Altman is on the list because he writes about AI, not because the accord names him. More people can be added later.

**Who does what**
- **Jeff** (AI) designs and builds the watcher.
- **lcRachel** (AI, built on ChatGPT) reads what the watcher finds and writes the summary, citing her sources.
- **Debbie** (AI) reviews the code and spot-checks the summaries against the original articles.
- **A person** picks the story and the sources, and signs off before anything goes live.

**How we keep it honest:** every claim in a summary must point to the page it came from. If a source does not say something, the summary says "not found" instead of guessing.

**What is verified:** the text of the accord itself, which Jeff fetched and read. Everything else about the meeting is unverified until we find sources for it.

## 1a. Primary source (fetched 2026-10-02)
White House Accord on Super Intelligence, "Joint Commitment on Frontier Responsibilities", dated September 29, 2026, hosted by The American Presidency Project: https://www.presidency.ucsb.edu/documents/white-house-accord-super-intelligence (the link we were given carried a `utm_source=chatgpt.com` tracking suffix, dropped here). Saved text: `captured/2026-09-29-white-house-accord-on-super-intelligence.txt`.
What the page says (Jeff's reading of the text, not an interpretation of intent):
- Each company that trains and deploys frontier models should implement four layers: (1) internal controls monitoring capabilities and alignment (cybersecurity, biosecurity, chemical threats, no unintended hacking or system access); (2) an internal team that checks the controls work and fixes issues; (3) an independent external auditor or evaluator; (4) an independent board committee that oversees reports and remediation.
- The participating companies "will meet regularly to establish standards and best practices to improve the safety of their systems".
- It may make sense to codify the steps into laws or regulations over time; the companies commit to the controls regardless.
- Signature block lists: Donald J. Trump (President), Sundar Pichai (Google), Dario Amodei (Anthropic), Mark Zuckerberg (Meta), Greg Brockman (OpenAI), Elon Musk (xAI), Jensen Huang (Nvidia).
Note for the watch list: the OpenAI signature on this page is Greg Brockman, not Sam Altman. Jeff does not know whether Altman attended the meeting; this page does not say. The watcher should therefore not be limited to Altman.

## 2. Scope
In scope: watch a list of sources, match new items against rules, save matches, summarize with citations, notify TB.
Out of scope for v0.1: publishing anything, sentiment or opinion output, social media scraping, any change to LabChan code, Rachel's code, or her model.

## 3. Why two parts
lcRachel only acts when a message reaches her and she has no search or schedule of her own. She also invents details when she has no source (2026-10-02 tests). So:
- Part 1, the **watcher** (a plain script on a schedule): no model calls, no token cost. It finds and saves.
- Part 2, the **summarizer** (lcRachel): runs only when the watcher has a match. She is given the saved text and told to cite and say "not found" when a source is silent.

## 4. Watcher design (PROPOSED)
1. **Sources list** (`sources.json`, edited by TB): each entry is a feed URL or page URL, plus a label.
   - Candidates, to be verified before use: Sam Altman's blog feed, the OpenAI blog feed, Dario Amodei's essays and the Anthropic news page, other participants' company blogs, a Google News RSS search for the story (the same mechanism Pulse uses for ad-hoc topics, last 24 hours), and the main outlets (AP, NPR, PBS, Politico, The Hill, ABC, CBS, Axios).
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
2. People and organizations to watch: Sam Altman and Dario Amodei first (both write often). The accord's signature block also names Pichai (Google), Zuckerberg (Meta), Brockman (OpenAI), Musk (xAI) and Huang (Nvidia); add any of them, and decide whether to watch company blogs as well.
3. Notify channel: LabChan to TB, email, or both.
4. Check frequency: for example every 30 minutes, hourly, or twice a day.
5. Where the saved articles live (suggest the repo's `captured/` folder, not tracked in git).
6. Whether Rachel summarizes automatically or only when TB asks.

## 8a. Decisions made (2026-10-03)
1. **Sources:** Sam Altman's blog feed; the OpenAI news feed; Dario Amodei's essays and the Anthropic news page; a Google News search for the story.
2. **People to watch:** Altman and Amodei first, plus the other signers of the accord: Pichai (Google), Zuckerberg (Meta), Brockman (OpenAI), Musk (xAI), Huang (Nvidia).
3. **Notify:** a LabChan message to the project owner, and an email to the owner's address. The address lives in a local config file and is never committed to this public repo.
4. **How often:** twice a day.
5. **Where articles are saved:** the repo's `captured/` folder (kept out of git).
6. **Summaries:** lcRachel summarizes every match automatically.

### Source check (2026-10-03, read-only)
Jeff fetched each candidate to see what the watcher can actually read:
- Sam Altman's blog: a working Atom feed (`posts.atom`). Easy.
- OpenAI news: a working RSS feed (`rss.xml`). Easy.
- Google News search: a working RSS feed for a search query, last 2 days. Easy.
- Anthropic news: an ordinary web page, no feed found. The watcher would read the page and pick out new article links. Medium.
- Dario Amodei's site: an ordinary web page, no feed (`feed.xml` returned 404). Same approach as Anthropic: watch the page for new essay links. Medium.
Because three sources are feeds and two are pages, the first build handles feeds first and adds page-watching second.

### What this changes in the design
- Twice a day keeps the model cost tiny: at most a few lcRachel calls per run, far under her hourly ceiling.
- With summaries automatic, the "unchecked" label stays on every summary until Jeff or Debbie spot-check it (section 7).
- Still needed before any build: approval of this design by the project owner, Debbie's code review, and deploy approval, as in section 10.

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
