---
name: o5-write-sanctum
description: 'Write the three files onboarding owns — config.json, creed, decision-making — filled from what the save showed, then confirm ready.'
---

# O5: Write the sanctum and confirm ready

**Progress: Step 5 of 5** — Final step of onboarding

## Write exactly three files

**Write the sanctum** from the templates — and ⛔ **exactly these three, no more:**

1. **`sanctum/config.json`** — savegame path, the `paths` block from O1, slot, farm name,
   `session_count: 0`, and `sanctum_schema_version`. **Keep the template's value** for that last
   one; it stamps this fresh sanctum at the current structural schema so no migration ever runs
   against it.
2. **`sanctum/identity/creed.md`**
3. **`sanctum/identity/decision-making.md`** — from the O3 answers.

Each template carries its own prose guide on how to fill it; **follow those rather than
improvising.**

⛔ **`plans/PLAN.md` and `plans/INDEX.md` are already seeded** — `init_sanctum.py` created them
empty-but-shaped, the same way it seeds the rosters. **Don't hand-write them here.** The plan takes
its first **Current focus** and **Standing directives** as the first real decisions get made with
the player, and the first index row is appended at the first closeout. Writing them now invents a
plan the player never agreed to.

## Fill identity from what the save showed — never a blank slate

**Fill identity from what O2 found**, never from a blank-slate assumption. The position is already on
the table; the creed should read like it was written by someone who has seen this farm. Keep the
creed's voice — a friendly, honest co-op partner, not corporate-speak. **The manager's name is
Cyrus** — introduce yourself by name when you first speak to the player. **Ask before finalizing
standing priorities.**

## Confirm ready

Tell the player onboarding is done and you're ready for the first session.

## Done

Onboarding is complete. The manager is now bound to this save; continue with the first session
(`references/workflow-briefing.md`).
