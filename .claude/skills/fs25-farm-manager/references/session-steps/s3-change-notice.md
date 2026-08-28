---
name: s3-change-notice
description: 'State what moved since last session from a record that computed it — and say in-band when that record does not exist yet.'
nextStepFile: './s4-evaluate-duties.md'
---

# S3: Read the change notice

**Progress: Step 3 of 5** — Next: Evaluate the duty register

**State what moved since last session.** The intended source is the delta log —
`sanctum/history/delta-log.jsonl`, whose last entry is a record that *computed* the change rather
than a diff you reconstruct by eye. Read that entry and report from it.

## ⛔ The delta log does not exist yet — degrade, and say so IN BAND

**The delta-log artifact is not built.** Do not pretend it is, and do not silently substitute the
fallback: **degrade to diffing `history/closeout-latest.md` against the state view S2 delivered,
and tell the player that is what you did**, in the briefing itself — not in a footnote, not only
in the friction log.

One line is enough: *"Change notice is a hand diff against last closeout — the computed change
log isn't built yet, so treat 'what moved' as my reading rather than a record."*

**A degradation the player cannot see is indistinguishable from a full answer**, which is the
whole reason this is stated in-band. The diff itself is the same content either way: days passed,
crops grown or harvested, contracts completed or expired, money moved, storage filled, animals
needing attention.

## When the record does exist, a `gap` is not a rate

A delta-log entry may itself carry a `gap` record — sessions the log did not observe. **Render
that as `status: partial` with the gap named** (which sessions, and why), **never as a
completeness rate.** A percentage invites the reader to treat the missing part as noise; a named
gap does not. And a `gap` is never rendered as "nothing changed" — an unobserved session is not
a quiet one.

## Next

Once you know what changed — and have said how you know it — read fully and follow: {nextStepFile}
