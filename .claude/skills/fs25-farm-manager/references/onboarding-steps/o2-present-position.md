---
name: o2-present-position
description: 'Take delivery of the state view, then show the player the real position before asking them anything.'
nextStepFile: './o3-profile.md'
---

# O2: Take delivery and present the position

**Progress: Step 2 of 5** — Next: The profile conversation

## Take delivery of the state view

This farm has no cache yet, so generate one and then read it through the gate:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/generate_state.py" --config sanctum/config.json
python3 ".claude/skills/fs25-farm-manager/scripts/read_state.py"     --config sanctum/config.json
```

**The trust contract from S2 applies here in full** — read EVERY signal the fleet uses, never the
exit status: a top-level `error` key, **`calibration_needed`** ("could not confidently parse this
source" — distinct from a section being unresolved and from `error`), and per-section **`resolved`**
/ **`status`** / **`why_unresolved`** (a section can be honestly *unresolved* with no `error` at
all). Also detect the envelope on `"sections"` and never on `"status"`, surface a `blocked_by`
distinctly, and **stop rather than present a view you have judged untrustworthy.** Onboarding is the
worst possible moment to guess: the player is about to answer questions whose premise is whatever
you show them now.

**The position itself — cash, loan, owned land, fleet — comes from `farm_snapshot.py`, one call, not
from hand-picking fields out of the cached view above:**
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/farm_snapshot.py" "<savegame_path>" --farm-id <config.farm_id>
```
It carries the same never-imply-false-by-omission contract as the cache — every section states its
own `status`, and a missing/errored source is a visible `unavailable`, never a silent gap. Read it
the same way: per-section, not by exit code.

⚠ **This is the first run this farm has ever made — the coldest moment the skill has.**
`equipment_gaps` alone can legitimately take up to 120s here (measured: 37.9s cold, 15.8s warm). A
slow `equipment_gaps` section on THIS call is not grounds to halt onboarding, only grounds to say so
plainly if it comes back degraded. **This allowance is scoped to that one named section** — an
actual `error` on any other section still stops you exactly as the trust contract above requires.

## Plus exactly one `read_career.py` call — for six fields and no more

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/read_career.py" "<savegame_path>"
```

⛔ **This call exists for six fields the state view does not carry, and this is the complete list:**

1. **map**
2. **difficulty**
3. **the save's *starting* money and loan** — the opening figures, not the current position
4. **`timeScale`**
5. **`autoSaveInterval`**
6. **the mod list**

**All six, every onboarding.** This is a narrow, named exception to reading state through the gate —
not a licence to reach for a raw dump. **Do not widen it** to anything the state view already
answers, and **do not drop one of the six** because it seems minor: `timeScale` alone decides
whether every "days until X" you ever say is sound or absurd, and the starting money/loan is the
only baseline the farm's whole financial history is measured from. A shorter list is not a tidier
version of this step — it is a different step that loses data nothing else supplies.

## Present the real position — before asking anything

**Present the real position to the player, plainly**: cash, loan, owned land, fleet, day/season,
difficulty.

⛔ **Position precedes every question.** This ordering is load-bearing and it is not a matter of
style. It is the fix for a real and expensive mistake (F-010): an earlier session asked the player a
planning question while genuinely believing — from a since-fixed parser bug — that the farm was a
blank slate. It actually owned 18 parcels, 24 machines, and millions in debt-funded iron. **The
question got answered on a false premise, and three sanctum files had to be rewritten afterwards.**

Showing the position first is what makes the next step's questions meaningful, and it is also what
lets the *player* catch a bad read before it becomes a decision. If anything in the view came back
degraded or blocked, say so here rather than presenting a partial position as a whole one.

## Next

Once the real position is on the table, read fully and follow: {nextStepFile}
