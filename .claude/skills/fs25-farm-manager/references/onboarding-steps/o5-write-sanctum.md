---
name: o5-write-sanctum
description: 'Write the three files onboarding owns — config.json, creed, decision-making — filled from what the save showed, then confirm ready.'
---

# O5: Write the sanctum and confirm ready

**Progress: Step 5 of 5** — Final step of onboarding

## Write exactly three files

**Write the sanctum** from the templates — and ⛔ **exactly these three, no more:**

1. **`sanctum/config.json`** — savegame path, the `paths` block from O1, slot,
   `player_name` and `language` from **O1**, `session_count: 0`, and `sanctum_schema_version`.
   **Keep the template's value** for that last one; it stamps this fresh sanctum at the current
   structural schema so no migration ever runs against it.
   ⚠ **`farm_name` is already written — O2 recorded the player's answer before the state gate ran.**
   Carry it through unchanged. Re-deriving it here, or overwriting it with the save's own name,
   discards an answer the player gave.
   ⛔ **Leave no `{{...}}` placeholder in a live config.** `sanctum_maintain.py check` reports a
   *missing* required key, but an unanswered placeholder sitting in a present key reads to every
   check as an answer. `player_name` and `language` were asked at the very top of **O1**,
   before any command ran: write what the player said.
   ⛔ **Never write the literal `"unknown"` into `player_name` or `language`.** Both are in
   `CONFIG_REQUIRED_KEYS`, and the judgement `sanctum_maintain check` imports
   (`aggregate_render._is_placeholder`) classifies `"unknown"` as a placeholder — so the farm
   would report **STALE every session** until someone hand-edited the file. `templates/config.json`'s
   own guide for these keys says the same; this is not a style preference. ⚠ **Any answer is an
   answer**: *"just call me farmer"* is a complete reply, so record **that**. Both keys were asked
   at O1, so by the time you reach this step a real answer exists to write — if one somehow does
   not, go back and ask rather than inventing a filler.
2. **`sanctum/identity/creed.md`**
3. **`sanctum/identity/decision-making.md`** — from the doctrine answers O3 collected.
   ⛔ **Its language line is a POINTER to `config.json`'s `language` and must stay one** — don't substitute the chosen language
   into it. `player_name` is frozen, so the creed restates it; `language` is a preference the player
   can change, and a mutable value held in two files is how one starts quietly lying.

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

Tell the player onboarding is done and you're ready for the first session — **in the language they
chose at O1**, and **by their name**. This sentence is the first thing that shows whether either
answer was actually recorded or merely heard.

## Done

Onboarding is complete. The manager is now bound to this save; continue with the first session
(`references/workflow-briefing.md`).
