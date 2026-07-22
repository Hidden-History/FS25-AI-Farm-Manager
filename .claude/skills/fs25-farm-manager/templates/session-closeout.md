---
class: briefing-snapshot
load: C
owns: "one session's closeout draft — the diff + narrative, not a re-archive of what durable files already hold"
cap_lines: 90
cap_kb: 5
rotation_trigger: none
archive_target: N/A
reconciliation: "verification not reconstruction; never restate a friction-log entry (cite its ID); durable substance goes to the family-1 file it concerns, not here"
format_version: 1
parity_spec:
  required_sections: ["## State delta", "## What we did / what changed", "## What didn't work", "## Open threads for next time", "## Plan updated", "## Frictions this session"]
---

# Closeout — {{DATE}} (Session #{{SESSION_NUMBER}})

*In-game open/close time + elapsed, `timeScale`: {{TIMES}}. Write in three passes — fill the table
from `farm_snapshot.py`'s digest (never estimate a delta you didn't read), then 3–6 bullets of what
happened, then the honesty sections. If most fields already changed during the session (the
"write as you go" rule), this file is verification, not reconstruction.*

## State delta

Durable headline numbers only — Open / Close / Δ. This is what caught session 1's silent parcel
purchase; keep it a table, not a running commentary.

| Metric | Open | Close | Δ |
|---|---|---|---|
| Cash | {{}} | {{}} | {{}} |
| Loan | {{}} | {{}} | {{}} |
| Fleet (count / value) | {{}} | {{}} | {{}} |
| Land (parcels / ha) | {{}} | {{}} | {{}} |
| {{other durable-state number this farm cares about}} | | | |

## What we did / what changed

{{3–6 bullets, highlights only. Point to `state/field-dossiers/`, `plans/PLAN.md`,
`state/equipment-roster.md` for detail — they were written during the session, so this verifies.}}

## What didn't work

{{The highest-value section. A *recommendation/decision* that missed — wrong advice, a sell timed
badly, a plan abandoned — narrative, 2–4 sentences per item, max ~4 items. If an item is also a
friction-log analysis error, cite its ID (`see F-108`) — do NOT re-narrate it here (session 1 wrote
the same seven mistakes twice, once here and once as F-101–F-107). "Nothing missed today" is valid
and complete.}}

## Open threads for next time

{{Bullets, capped ~6–8, one line each. If something needs multiple sentences (a grace-period
warning), it belongs in the durable file it concerns (`state/crop-grace-periods.md`, a field
dossier) with just a pointer here.}}

## Plan updated

{{Pointer only — what changed in `plans/PLAN.md` (Current focus rewritten? directives opened,
touched, or closed?) and the session-plan file written this closeout, or "none this session."
Never restate the plan text — `plans/sessions/{{DATE}}-session-{{SESSION_NUMBER}}.md` and
`plans/PLAN.md` own it. See `closeout-steps/step-06-update-plan.md`.}}

## Frictions this session

{{Pointer only, one line: "N entries appended to `history/friction-log.md` (F-xxx…F-yyy)." Don't let
"What didn't work" erode into a second copy of the friction log.}}

---
*This closeout overwrites `sanctum/history/closeout-latest.md` and is archived to
`sanctum/history/journal/{{DATE}}-session-{{SESSION_NUMBER}}.md`.*
