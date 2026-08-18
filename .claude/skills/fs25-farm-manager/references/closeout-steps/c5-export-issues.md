---
name: c5-export-issues
description: 'Triage this session''s frictions for exportability, PII-scan the rendered text, and offer each one to the player individually before anything leaves the farm.'
nextStepFile: './c6-signoff.md'
---

# C5: Export issues

**Progress: Step 5 of 6** — Next: Sign off

This is the only step that sends anything off the farm. Everything below exists to make sure what
leaves is exactly what the player saw and approved — nothing scanned-but-unseen, nothing batched,
nothing silent.

## 1 · Find what's exportable

Read `sanctum/history/friction-log.md`. A candidate is any entry whose `github:` field reads
`not-exported` — or is missing entirely, for an older entry written before this field existed.

Apply the triage rule from `## What belongs here`: exportable only if a fix in the shipped skill or
mod would prevent this recurring on another player's farm. An entry that's your own analysis error
or a this-farm judgement call is not a candidate — write `github: not-applicable` on it now and
leave it out of everything below.

**If there are no candidates, that's a complete outcome, not a gap.** A farm with a clean log, or
one where every open entry is already `not-applicable` or already carries a URL, has nothing left
to offer. Don't skip the question below to get there — ask it anyway, and let "zero" be the answer
you report, not the reason you went quiet.

## 2 · Ask before doing anything else

**"These N frictions look like product defects. Send any to GitHub?"** — N is the candidate count
from step 1 (zero is a valid N).

**If the player declines** — "not now," "no," or anything short of yes — stop here. Leave every
candidate's `github:` exactly as it was (still `not-exported`), so they're offered again next
session, and move on to the second question in step 6. Declining is a complete, valid outcome; say
so plainly and don't press.

If they want to see them, continue to step 3 — one candidate at a time, never a batch.

## 3 · Render each candidate — title and body

For every candidate, render the actual issue text: a one-line title, and a body built from the
entry's What / Truth / Impact / Fix / Lesson. **Omit the farm's finances unless the money IS the
defect** — a report about a parser returning `null` doesn't need the player's balance; a report
about currency formatting does.

## 4 · Scan before the player sees a draft

Before showing anyone the rendered text, scan it:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/pii_scan.py" --text "<rendered title + body>"
```

- **exit 0** — ran, nothing matched. Tell the player exactly what ran: *"Scanned for usernames,
  home paths and author identifiers."* Never say "PII gate passed" or "scanned for personal
  data" — either would leave the player reasonably believing their finances were checked, and they
  were not.
- **exit 1** — ran, matched at least one pattern. ⛔ **Do not publish, and do not silently fix and
  resend — refuse and show the player what matched** (`matches[].why`) so they can edit the text
  themselves and you can rescan. A redaction the player didn't see is a change they didn't approve.
- **exit 2** — ⛔ **the scan did not run** — bad usage or an unreadable file. This is a refusal, not
  a clean result: treat it exactly like exit 1. Do not publish, and say plainly that the scan
  couldn't run and why (the `error` field), never "nothing found."

## 5 · Offer each one, individually

⛔ **One issue at a time, never a batch offer.** For each candidate that scanned clean, show the
player the exact title and body that would be posted, the scan result, and the triage reason it
qualified. They approve, edit, defer, or drop **that one entry** — silence is never approval, and
there is no "approve all" shortcut. Re-scan if they edit the text before it's posted.

If approved: this project's own tracker is
`https://github.com/Hidden-History/FS25-AI-Farm-Manager/issues`. **You ask whether to post; you do
not detect whether you can** — don't go looking for `gh`, credentials, or network access first.
Work out with the player how it actually gets there: if `gh` is set up and they want you to use it,
use it; otherwise, or if you're unsure, hand over the rendered title and body and let them post it.
Either way, write the result back per step 7 below.

If the player defers or drops it: leave `github:` as `not-exported` (defer) or set it to
`not-applicable` (drop) and move to the next candidate.

## 6 · The second question — every closeout, regardless of the first answer

**"Anything else you want added or changed — including things that aren't defects?"** — this is
the only route by which what the player *wants* reaches the repo; the friction log only records
what went wrong. Ask it even if step 2 was declined; the two questions are independent.

Anything offered here is rendered and scanned exactly like steps 3–4, shown for the same per-item
approval as step 5, and posted tagged `enhancement` rather than `bug`.

**If the player declines this one too**, that's equally a complete, valid outcome — say so plainly
(*"noted, nothing sent this session"*) and move on to sign-off; nothing here blocks the closeout.

## 7 · Write back

For every candidate that was posted, write its issue URL into `github:` on that exact entry in
`sanctum/history/friction-log.md`. This field is the whole dedup mechanism — skip it and the same
friction gets offered again next session.

## Next

Once both questions have been asked, every approved candidate resolved, and the `github:` field
written back, read fully and follow: {nextStepFile}
