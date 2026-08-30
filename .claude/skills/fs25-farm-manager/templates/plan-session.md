---
class: briefing-snapshot
load: C
owns: "one session's plan record — what was decided and how the main plan changed, not a re-statement of the plan itself"
cap_lines: 90
cap_kb: 6
rotation_trigger: none
archive_target: N/A
reconciliation: "one file per session, written at closeout; records the decisions plus the deltas folded into plans/PLAN.md; never restates a standing directive (points at it)"
format_version: 1
parity_spec:
  required_sections: ["## Decided this session", "## Plan changes", "## Plan vs reality", "## Carried into next session"]
---

# Session Plan — {{DATE}} (Session #{{SESSION_NUMBER}})

_What this specific session decided and how it changed the farm's plan — the per-session
companion to `plans/PLAN.md`. The main plan holds the current, synthesized state; this file
holds the record of how it got there this session, so a later "why did we decide X" is
answerable without archaeology. Write it at closeout, from what was actually decided — not a
wishlist. If most of the plan was already updated during the session (the write-as-you-go
rule), this file is a record, not a reconstruction._

## Decided this session

{{The real decisions, 2–5 bullets — a crop choice, a purchase agreed, a route resolved, a
question answered. Cite the evidence that settled each one where a number did the work (a save
figure, a dossier read) — the same discipline the main plan uses. "No plan decisions today" is
a valid, complete entry.}}

## Plan changes

{{Pointer, not restatement — what changed in `plans/PLAN.md` this session: directives opened,
touched, or closed (name them; do not re-narrate — the entry in PLAN.md owns the text), and
whether the Current focus narrative was rewritten and why. "PLAN.md unchanged this session" is
valid.}}

## Plan vs reality

{{The cross-check that keeps the plan honest: does anything in `plans/PLAN.md` now contradict
the live sanctum — a field dossier, the finances ledger, a roster? A directive that assumes a
field is fallow when its dossier says it is planted; a focus item that assumes cash the ledger
says is gone. Flag the contradiction here and fix the plan. If nothing contradicts, say so —
"plan reconciles with dossiers, ledger, roster" — but only after actually looking, never as a
reflex.}}

## Carried into next session

{{The open threads this session hands forward, one line each — what next session's briefing
should pick up. Bullets, capped ~6. Anything needing more than a line belongs in the directive
or dossier it concerns, with just a pointer here.}}
