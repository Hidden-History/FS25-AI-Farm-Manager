---
name: c2-session-record
description: 'Write the session record in one pass — the closeout saved twice, this session''s ledger row completed, and the friction log appended.'
nextStepFile: './c3-close-plan.md'
---

# C2: Write the session record

**Progress: Step 2 of 5** — Next: Close the plan

**This is one write pass, not four.** The closeout, its second copy, the ledger row and the
friction log are all the same act — recording what this session was — and doing them as one pass is
what stops the fourth from being forgotten because the first three felt like finishing.

## 1 · Write the closeout

**Write the closeout** using `templates/session-closeout.md` as the shape. Fill in "What didn't
work" honestly — a recommendation that missed, a contract that wasn't worth it, a sell timed badly.
This is what stops next session repeating the mistake.

Don't skip it, and don't pad it. **"Nothing missed today" is a valid entry; an invented failure is
not** — a fabricated lesson is worse than no lesson, because a future session will act on it.

## 2 · Save it twice, deliberately

**Archive to `sanctum/history/journal/{{date}}-session-{{n}}.md`, then overwrite
`sanctum/history/closeout-latest.md` with the same content.** The archive is history;
`history/closeout-latest.md` is what next session actually reads.

⛔ **Same content, both places, in the same pass.** These are two different jobs — writing only one
silently breaks either the record or the handoff, and neither failure announces itself. **S1 reads
`closeout-latest.md` and nothing else**, so a journal entry without the overwrite is a session the
next briefing cannot see.

## 3 · Complete this session's ledger row — never append a second

Read `sanctum/state/finances-ledger.md`. **This session's row was opened at session start as an
opening snapshot; complete that row's Notes now.**

⛔ **Never append a SECOND row for this session.** Rows are opening snapshots. A dedicated closeout
row alongside a real opening one would mix opening and closing figures across two rows and quietly
corrupt the cross-session trend — the very thing the ledger exists to show. **One row per session,
always** — but if this session genuinely has no opening row at all (session start skipped it, or
never opened one), the disclosed write is PERMITTED and preferred over silence: **write one row now
and say so, in its Notes** — e.g. *"opening row written at closeout; session started without one."*
That is one row, honestly labelled, not a second. Only when you cannot even do that — you cannot
determine what the opening figures would have been — say so in the friction log instead of guessing
at values to backfill. `references/sanctum-upkeep.md` holds the full contract.

## 4 · Append this session's frictions

**Append to `sanctum/history/friction-log.md`** (create from `templates/friction-log.md` if
absent). ⛔ **Append — never overwrite; it is cumulative.**

Every issue, error, and friction: **your own analysis errors first** (a wrong generalisation, a bad
regex, an error object read as data, a truncated listing believed as an inventory), then script
bugs, **silent wrong answers especially** (a clean plausible incomplete result with no caveat is
worse than an error), anything you had to hand-roll because no script existed, anything you wrote
freehand because no template existed, any portable `references/*` file caught asserting
farm-specific facts, and anything the player had to tell you twice.

**This is not the same as the closeout's "What didn't work."** That is per-session, narrative, and
gets overwritten in `history/closeout-latest.md`. This is the standing defect list — it accumulates
and entries stay until fixed. **Both, every time.**

Same honesty rule: **an invented friction is worse than none.** But note how rare a real zero is —
if this file gains nothing after a long session, that omission is itself the friction.

## Next

Once the record is written, saved twice, the row completed and the frictions appended, read fully
and follow: {nextStepFile}
