# lcRachel summary instructions (draft v0.2)

**Date:** 2026-10-04
**Status:** Draft, not yet used on real watcher items. Written by Jeff.

## Purpose

How to ask Rachel to summarize a web page for Politics AI, what the bridge now does for her, and what we learned testing it on 2026-10-04. The short version: she quotes well when the page has the answer, but she can fill a gap with a quote that does not support her claim, so a person still checks each claim against its quote.

## What the bridge does (since 2026-10-04, commit 410b13b)

For every `fetch-page:` request the bridge:

- starts from a clean slate: no saved conversation chain, no recent messages, no "recent exchanges" memory (pinned facts the owner taught her stay);
- adds grounding rules: answer only from the page, quote whole sentences word for word, a name is not a job title, write "not found" if no sentence states the answer, report a stated absence ("contains no legal enforcement mechanism") instead of listing it as missing, add nothing;
- does not save the answer into her conversation history, so one answer cannot leak into the next. The cost: a follow-up question that does not repeat `fetch-page:` will not know the page.

Nobody needs to paste the rules any more.

## How to ask

```text
rachel, fetch-page: <url>
Give the three main points. For each: one sentence in your own words,
then one whole-sentence quote from the page that supports it.
Say who said or did each thing exactly as the page says.
```

The "own words plus a quote" format is the most useful, because it makes each claim checkable. Always include the colon after `fetch-page`.

## What we found (tests of 2026-10-04)

1. **Bare questions on the accord page** (`gpt-4o-mini`): good quotes. Asked for a job title the page does not give, she answered with the person's name (wrong). Telling her "not found" is an acceptable answer fixed it.
2. **Earlier answers leaked.** On a news article, she reused two quotes from a different document and wrote "Who Signed: not found" although the article named signers. Cause: her saved chain and "recent exchanges" memory carried her earlier answers into the new request. Fix: the fresh-context change above. Repeating the same request afterwards produced no off-page quotes.
3. **After the fix**, her summary of the article was mostly right but had two slips: a collaboration remark credited to Trump that Amodei made, and Musk's "AI"/"S.I." slip described backwards. With the "own words plus quote" format the backwards slip went away, but two claims were paired with real quotes that did not support them (a whispered exchange claim backed by a sentence about something else).
4. **Same-model second pass** (Rachel judging seven claim and quote pairs, two of them bad): she caught the clear mismatch, approved the looser one, and answered "not found" to one pair instead of yes or no. A model checking its own work is not a reliable verifier.

## Checks

- A script confirms each quote appears on the page (catches invented quotes).
- A person reads each claim against its quote (catches real quotes that do not support the claim). This step cannot yet be automated reliably.
- Next experiment: a different or stronger model (or Debbie) as the second-pass checker.

## Limits

- Small sample, one model (`gpt-4o-mini`), one article and one page. Repeat before relying on any of this.
- She reads only what the bridge fetches: text, up to 20,000 characters. Long pages are cut off.
- She sometimes paraphrases instead of quoting, and sometimes quotes a fragment instead of a whole sentence.
- Do not publish a summary without the checks above.
