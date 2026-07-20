---
name: step-05-append-friction-log
description: 'Append this session''s frictions to the cumulative friction-log — never overwrite; include anything the honesty check reported.'
nextStepFile: './step-06-verify-sanctum.md'
---

# Step 5: Append this session's frictions

**Progress: Step 5 of 7** — Next: Walk the sanctum and verify each file

**Append this session's frictions to `sanctum/history/friction-log.md`** (create from
`templates/friction-log.md` if absent). **Append — never overwrite; it is cumulative.**

Every issue, error, and friction: **your own analysis errors first** (a wrong
generalisation, a bad regex, an error object read as data, a truncated listing believed as
an inventory), then script bugs, **silent wrong answers especially** (a clean plausible
incomplete result with no caveat is worse than an error), anything you had to hand-roll
because no script existed, anything you wrote freehand because no template existed, any
portable `references/*` file caught asserting farm-specific facts, anything step 4's
honesty check just reported, and anything the player had to tell you twice.

**This is not the same as step 2's "What didn't work."** That is per-session, narrative,
and gets overwritten in `history/closeout-latest.md`. This is the standing defect list — it
accumulates and entries stay until fixed. Both, every time.

Same honesty rule: **an invented friction is worse than none.** But note how rare a real
zero is — if this file gains nothing after a long session, that omission is itself the
friction.

## Next

Once this session's frictions are appended, read fully and follow: {nextStepFile}
