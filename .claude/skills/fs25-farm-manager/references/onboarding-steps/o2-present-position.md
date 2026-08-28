---
name: o2-present-position
description: 'Confirm the farm name the state gate requires, take delivery of the state view, then show the player the real position before asking them anything else.'
nextStepFile: './o3-profile.md'
---

# O2: Take delivery and present the position

**Progress: Step 2 of 5** — Next: The profile conversation

## First, confirm the farm's name — before anything reads the config

⛔ **This question comes before the two commands below, and the ordering is the fix.**
`read_state.py` renders through `aggregate_render.build_header`, which **refuses** a `farm_name`
that is unset or still a placeholder — correctly, because falling back to the sanctum directory
name would put a filesystem accident in front of the player as their farm's name. O1 bound the
save but recorded no name, so a fresh sanctum arrives here with nothing to render and the **whole
view is refused** before the player has ever been asked (BUG-025 (iii)).

`locate_save.py` already showed you this save's own farm name, read from `farms.xml`. **Put it to
the player as a question, not as a fact** — *"your save calls this farm X; is that what I should
call it, or do you have another name for it?"* — and record **their answer** as `farm_name` in
`sanctum/config.json`.

⛔ **Ask first, then write. Never write a name and ask for confirmation afterwards.** Writing a
default and confirming it later satisfies the gate **without answering the question**: no error is
ever emitted, onboarding completes cleanly, and an invented name sits in the config reading exactly
like an answered one. That is what happened live, and it is why this step exists. The save's own
name is a **candidate to confirm**, never a value to record before the player has spoken.

⚠ **This is the only question ON THIS STEP that precedes the position display, and the exemption
is narrow.** F-010's rule below governs **judgment** questions — the ones whose answers are only
meaningful once the player has seen the real position. `farm_name` is not one of those: it is an
**input the read itself requires**, so it can never be informed by a read that cannot run without
it. ⚠ **`player_name` and `language` were already asked at the top of O1**, under a separate and
equally narrow exemption: they are identity **data**, not judgments, so no briefing could inform
them — and every sentence this step speaks is spoken in some language, so asking later means
having already got it wrong. **Those three keys are the whole list.** Nothing else on this step,
and nothing on O3, gets an exemption.

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
