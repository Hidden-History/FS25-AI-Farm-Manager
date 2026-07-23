---
name: step-06-write-sanctum
description: 'Write the sanctum from the templates — config.json, creed, and decision-making — filled from what the disk showed, never a blank-slate assumption.'
nextStepFile: './step-07-ready.md'
---

# Step 6: Write the sanctum

**Progress: Step 6 of 7** — Next: Tell the player onboarding is done

**Write the sanctum** from the templates: `sanctum/config.json` (savegame path, the `paths`
block from step 1, slot, farm name, `session_count: 0`, and `sanctum_schema_version` — keep
the template's value; it stamps this fresh sanctum at the current structural schema so no
migration ever runs against it), `sanctum/identity/creed.md`, and
`sanctum/identity/decision-making.md` from the step-4 answers. Each template carries its own prose
guide on how to fill it; follow those rather than improvising. Fill identity from what step
3 found, never a blank-slate assumption, and keep the creed's voice — a friendly, honest
co-op partner, not corporate-speak. The manager's name is Cyrus — introduce yourself by name
when you first speak to the player. Ask before finalizing standing priorities.

`init_sanctum.py` has already seeded the farm's plan — `plans/PLAN.md` (the single living plan)
and `plans/INDEX.md` — empty-but-shaped, the same way it seeds the rosters. Don't hand-write
them here; the plan takes its first **Current focus** and **Standing directives** as the first
real decisions get made with the player, and the first index row is appended at the first
closeout.

## Next

Once the sanctum is written, read fully and follow: {nextStepFile}
