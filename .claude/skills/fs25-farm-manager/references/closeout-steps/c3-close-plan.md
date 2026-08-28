---
name: c3-close-plan
description: 'Verify plans/PLAN.md against what actually happened, then close or carry each directive — rewriting the Current focus in place, never appending.'
nextStepFile: './c4-verify-sanctum.md'
---

# C3: Close the plan

**Progress: Step 3 of 5** — Next: Verify the sanctum

The plan is the farm's intent, and a closeout that doesn't reconcile it is how a plan quietly rots
into fiction. This step is first-class and not skippable — do all three parts.

**1. Write this session's plan.** Create `plans/sessions/{{date}}-session-{{n}}.md` from
`templates/plan-session.md`: what was **Decided this session**, the **Plan changes** you folded into
the main plan, the **Plan vs reality** check below, and what's **Carried into next session**. Like
the closeout, this is a record of what actually happened — if you kept the plan current during the
session (write-as-you-go), this is verification, not reconstruction.

**2. Update the main plan.** Fold this session's changes into `plans/PLAN.md`:
- ⛔ **Rewrite the Current focus narrative in place** so it reflects where the farm now stands — it
  is a **synthesis, never an append-only log.** A focus section that only ever grows stops being
  readable, and next session reads it first.
- **Update the Standing directives**: open any new long-term item (from
  `templates/directive-entry.md`), touch every directive you looked at (even "reviewed, nothing
  new" — update its Last touched), and **close resolved ones honestly** — strike the title, mark it
  done/abandoned, and write the Outcome / What actually happened / Lesson.

⛔ **A closed directive records what ACTUALLY happened, even where that contradicts the directive's
own premise.** A directive that assumed something false is the most valuable one to close honestly,
and **a directive closed quietly erases its lesson** — which is the one thing it was keeping.

**3. Cross-verify the plan against the rest of the sanctum.** Read the plan against the live state
it depends on — the field dossiers, the finances ledger, the rosters — and **flag any place the plan
claims something the current state contradicts.** A directive that assumes a field is fallow when
its dossier says it's planted, a focus item that assumes cash the ledger says is gone: fix the plan
to match reality, and record the catch in the session plan's **Plan vs reality** section. If nothing
contradicts, say so there — **but only after actually looking, never as a reflex.**

**Append the index row.** Add one row to `plans/INDEX.md` (date, session #, in-game season/day, the
session-plan filename, and the session's headline decision) — **append only, newest at the bottom,
never rewrite a past row.**

## Next

Once the plan is written, updated, cross-verified, and indexed, read fully and follow: {nextStepFile}
