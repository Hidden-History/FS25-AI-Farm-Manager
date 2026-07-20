---
class: append-only-log
load: B
owns: "this farm's standing defect list — every analysis error, script bug, and friction, cumulative"
cap_lines: 150
cap_kb: 20
rotation_trigger: on-resolve+on-close-over-cap
archive_target: "history/archive/friction-archive-{YYYY}.md"
reconciliation: "live = OPEN + actionable-NOTED only; FIXED/NOTED whole entries relocate to the yearly archive with id preserved, never renumbered; OPEN never rotates"
format_version: 1
parity_spec:
  required_sections: ["## Open backlog", "## Why this file exists", "## Numbering", "## Status key", "## Rotation", "## What belongs here", "## Entry shape", "## The rule that matters"]
---

# Friction Log — {{FARM_NAME}}

**Every issue, error, and friction, cumulative across sessions.** Append-only *within a live
session block*; a resolved (FIXED/NOTED) whole entry may later relocate to cold archive with an
id-pointer (see Rotation) — that is not rewriting history, it's moving it.

This is **not** the closeout's "What didn't work" — that section is per-session and narrative, and
it gets overwritten in `history/closeout-latest.md` every time. This file is the **standing defect
list**: it accumulates, it survives sessions, and an entry stays until it is actually fixed.

## Open backlog

The live, actionable slice — regenerated (not appended) at every closeout, OPEN rows only. Ranked
by what it costs the player: wrong answers reaching the player first, then missing capability, then
papercuts. This replaces any bottom-of-file "ranked backlog" so the actionable list survives
rotation intact.

| ID | One-line | Cost if ignored | Session opened |
|---|---|---|---|
| {{F-NNN}} | {{what's still broken}} | {{what it costs if unfixed}} | {{session #}} |

## Why this file exists

The skill's own docs cite friction IDs (`F-001`, `F-010`, `F-023`…) as load-bearing evidence —
*"this exact mistake cost real money to find."* Those citations are only worth anything if the log
they point at exists and is readable. **A lesson referenced everywhere and recorded nowhere is not
a lesson.**

## Numbering

Pick an ID range that cannot collide with IDs already cited in the skill's own files
(`grep -rhoE "F-[0-9]{3}" <skill dir>` to see what's taken). Sort and start **above the highest ID
found**. Never renumber an existing entry — other files link to it, and an archived id is never
reused.

**Range used by this farm:** {{e.g. "F-201+, because grep found F-001…F-125 already cited"}}
**Next free ID:** {{NNN}}

## Status key

| | |
|---|---|
| **FIXED** | Corrected in place. Say **what changed and where** — a fix with no location is a rumour. |
| **OPEN** | Real, unfixed. This is the actionable backlog (top table). |
| **NOTED** | Understood; a lesson to carry, not a thing to patch. Most judgment errors land here. |

**NOTED-promotion rule:** a NOTED entry whose lesson should outlive this log must **also** be
written into `identity/decision-making.md` (or the relevant `references/*`) at the time it's noted.
That durable copy elsewhere is what makes the entry safely archive-eligible later — a NOTED entry
is not rotation-eligible until its lesson has been promoted.

## Rotation

Compound — `on-resolve` **and** `on-close-over-cap`:

- **OPEN never rotates** — it's the live backlog, it stays until actually fixed.
- **On resolve / over cap:** FIXED entries, and NOTED entries whose lesson has been promoted, are
  **moved whole** (never summarized) to `history/archive/friction-archive-{{YYYY}}.md` (yearly shard
  — farm session cadence is low), leaving a one-line banner pointer here. The id is preserved in
  `history/archive/friction-INDEX.md` (id → status → shard) so a cold entry stays findable.
- Regenerate the Open-backlog table after any move. Prove 0-lost before committing (the
  archive-not-delete conservation discipline); an archived id is never reused or renumbered.

## What belongs here

Log it if it cost time, produced a wrong answer, or nearly did:

- **Your own analysis errors** — a wrong generalisation, a bad regex, an error object read as data,
  a truncated listing believed as an inventory. **The most valuable entries and the easiest to
  quietly omit.** Nobody else will file them.
- **Script bugs** — wrong output, a false failure, a silent wrong answer (rank these first — a
  clean, plausible, *incomplete* result with no caveat is worse than one that errors).
- **Missing tooling / templates** — anything you had to hand-roll because none existed.
- **Docs asserting farm-specific facts in portable files** — a `references/*` file that says "none
  on this farm" is carrying some other farm's state, and no freshness probe reaches it.
- **Player corrections** — if they had to tell you twice, that's friction. Log it, and fix it in
  `identity/decision-making.md` so it survives the conversation.

## Entry shape

Keep entries diagnosable by someone who wasn't there. A defect list nobody can act on is a diary.

```markdown
### F-NNN — One-line summary · OPEN | FIXED | NOTED
**What:** What actually happened, concretely. Real values, real file names, real line text.
**Truth:** What was actually true, if the entry is an error. (Omit for pure gaps.)
**Impact:** What it cost, or nearly cost. Be honest — "nearly told the player X" counts.
**Fix (applied):** / **Fix needed:** What changed and where, or what should.
**Lesson:** The transferable rule. Skip it if there isn't one; don't manufacture one.
```

Group entries by session, newest at the bottom; within a session, analysis errors first (only you
can file them), then script/skill bugs, then missing tooling.

## The rule that matters

**An invented friction is worse than none** — a future session will act on it. "No frictions this
session" is a valid, complete entry when it's true. But be honest about how rare that is: a session
that read the save, ran the scripts, and talked to the player and hit *nothing* worth writing down
is a very short session. **If this file is empty after a long session, the omission is the friction.**
