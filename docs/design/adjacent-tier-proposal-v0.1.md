# Adjacent tier for the links page: proposal v0.1

Status: PROPOSAL for TB and Debbie. Nothing here is built or live. Written 2026-10-05.

## 1. What and why

The page today shows items about the central topic: the White House Accord on Super Intelligence and the
NVIDIA agent-safety announcements. TB found pages that are close to the topic but do not name it, for
example Rep. Ro Khanna's U.S.-China AI playbook and Sen. Bernie Sanders' bill to ban artificial
superintelligence. The watcher would never have caught them: they are not in any source it reads, and they
do not use the Accord's words.

This adds a second tier, **adjacent**, next to **central**. Each record says which tier it is in, the page
has a Topic column, and a switch at the top chooses what to show (default: Central only).

## 2. Decisions already made by TB (2026-10-05)

1. A Topic column, plus a filter switch at the top, defaulting to Central.
2. Adjacent items show on the page only. They send no LabChan alert.
3. First adjacent sources: a Bing News query, Khanna's "in the news" page, Sanders' press-release feed.

## 3. Data: a `tier` on every record

- New field `tier`: `"central"` or `"adjacent"`. A record with no `tier` (everything already in
  `state/seen.json`) counts as central, so no migration step is needed.
- Central rules and central sources are unchanged. An item that matches central is central, whatever source
  it came from.
- An item only becomes adjacent if (a) it did NOT match central, (b) its source is marked
  `"adjacent": true`, and (c) it matches the adjacent rules. Existing sources are not marked, so the
  Altman, OpenAI, NVIDIA, Malwarebytes, Anthropic and Amodei sources behave exactly as now.

## 4. Adjacent rules (`config/rules.json`, new `adjacent` block)

```json
"adjacent": {
  "since": "2026-09-15",
  "strong": ["superintelligence", "AI safety", "AI treaty"],
  "strong_combos": [["regulat*", "=AI"]],
  "weak": ["treaty", "inspection*", "safeguard*", "frontier", "binding", "AI risk*"],
  "min_weak": 2,
  "require_context": ["=AI", "=A.I.", "artificial intelligence", "superintelligence", "super intelligence"]
}
```

- Same matcher as today (`watcher/rules.py`), same whole-word and `*` and `=` rules, so no new matching code.
- Its own `since` (Sep 15, the first Sanders AI item), so the Sep 23 Sanders bill release is not cut off by the
  central `since` of Sep 28.
- **Tested on 16 real items** (Sanders feed 6, Khanna index 10, body text read for Khanna): 5 matched.
  - Correct: Sanders "Ban Artificial Superintelligence" bill; Sanders "Regulating AI is as American as apple
    pie"; Khanna "alternative U.S.-China AI playbook".
  - Borderline: Khanna "Trump has no cards left ... China summit" (mentions an AI treaty); "The WPI
    Conversation" (AI regulation and China).
  - Correctly left out: the Flock Act, heating assistance, UN remarks, solar, Epstein, gasoline, housing,
    removal-from-office and similar.
- A first attempt with generic words ("China", "Trump", "oversight") matched 4 unrelated Khanna items, so those
  words are NOT in the list. Expect to tune after a few days of real data.

## 5. Sources (`config/sources.json`)

Three new entries, all `"adjacent": true`, no change to the central ones.

1. **Sanders press releases**, a feed: `https://www.sanders.senate.gov/press-releases/feed/`. The existing
   feed parser reads it (checked: 6 items, titles, links, dates).
2. **Khanna in the news**, a page source: `https://khanna.house.gov/media/in-the-news`, link pattern
   `^/media/in-the-news/[^/]+$` (checked: 10 article links). Mostly non-AI, so the adjacent rules do the filtering.
3. **Bing News query**, a feed, for example `AI safety treaty China` (final words to be chosen with TB; Bing
   results are redirect-free, as the existing Bing source shows). Judged on title and summary only.

First run on each new source baselines silently, as the page watchers already do, so nothing floods the
page. Items dated on or after the adjacent `since` are looked at; older ones are remembered silently.

A PDF (such as the Sanders release summary) is not an item: the watcher reads no PDF text. The press-release
page that links to it is the item.

## 6. Page

- **Topic column**, between Headline and Source: `Central` or `Adjacent`.
- **Filter switch** above the table: two radio options, `Central` (selected by default) and `All`. It is
  pure CSS (radio inputs plus a sibling selector hiding `.adjacent` rows), so it needs no script and no
  change to the content policy. With Central selected, the page looks like today's.
- The "N link(s)" line counts what is shown, and notes how many adjacent items are hidden.
- The intro note says adjacent links are related, not about the Accord itself.
- No LabChan alerts for adjacent items.

## 7. Failure modes

- Noise: adjacent rules too loose. Mitigated by the default Central view and by tuning the word list.
- A source breaks: the existing 3-in-a-row failure alert already covers feed and page sources.
- A matcher mistake could send a central item to adjacent: central is evaluated first and is untouched;
  a test pins this.
- Older records without a `tier` stay central.

## 8. Tests (planned)

- tier defaults to central on old records; central matches stay central even from adjacent sources.
- an adjacent-only match becomes adjacent; a non-adjacent source never produces adjacent items.
- the adjacent block's own `since` applies; the central `since` does not cut adjacent items.
- page: Topic column and the radio switch are present; Central is selected by default; adjacent rows carry
  the `adjacent` class; the content policy is unchanged and has no script added.
- no alert is sent for adjacent items.
- the 16 examples above as a regression fixture.

## 9. Rollout

1. TB and Debbie review this page.
2. Build in git with tests; Debbie reviews the code.
3. Baseline the three new sources with `--baseline`; look at the first adjacent results by hand.
4. Publish with the next run. Review noise after about a week.

## 10. Questions for Debbie and TB

1. Is the adjacent word list right, or should `China`/`Trump`-style words stay out entirely (my suggestion)?
2. The Bing query wording.
3. Should the Topic column hide when the switch is on Central (it would be constant), or always show?
4. Any source the Anthropic and Amodei watchers should also feed into adjacent?
