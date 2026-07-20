---
class: register
load: C
owns: "the durable index of this farm's owned production chains — not their live running/fill status"
cap_lines: 80
cap_kb: 8
rotation_trigger: on-resolve
archive_target: "history/archive/production-roster-archive.md"
reconciliation: "stopped/removed chains MOVE to archive (never blind row-shed); Running/idle is live, Last updated is its confirm-date"
format_version: 1
parity_spec:
  required_sections: ["## Chains owned", "## Reading of it"]
---

# Production Chains Roster

_Snapshot: {{DATE}} ({{onboarding | updated at session N}}). Source:
`placeables.xml` production buildings filtered to this farm's `farm_id`._

**If this farm owns no production chains, say so explicitly and stop there --
don't leave the file looking unpopulated.** "0 production buildings owned as of
{{DATE}}" is a complete, correct entry -- a farm can be a perfectly fine harvest
or crop operation with zero production chains, and that's different from "never
checked." Update the snapshot date whenever this is re-verified, even if the
answer is still zero.

## Chains owned

_(Leave this section as "none" if it's true -- don't delete the section
heading.)_

| Building | Type | Running / idle | Last updated |
|---|---|---|---|
| {{BUILDING_NAME_OR_ID}} | {{TYPE — dairy, sawmill, bakery, etc.}} | {{STATUS}} | {{DATE}} |

**`Running / idle` is live** — `read_placeables.py` answers it fresh every session. `Last updated`
is its confirm-date, not decoration: don't trust a status older than the current session without
re-checking. The durable content here is the *list of chains owned* (the index); the status lives
in the save. When a chain is stopped or removed, MOVE its row to
`history/archive/production-roster-archive.md` — never blind-delete.

For each building above, keep a matching dossier (created from
`templates/production-dossier.md`) covering input/output fill levels, efficiency, and
history -- this roster is the index, the dossier is the detail.
`sanctum/state/production-dossiers/` is pre-created by `init_sanctum.py`
alongside `state/field-dossiers/` and `history/journal/` -- add a dossier
file the first time one is needed, the same way `state/field-dossiers/` is
populated on demand.

## Reading of it

{{If none owned: is this deliberate, or an open question worth a directive
(e.g. "decide whether a production chain is worth the input logistics")? If
owned: which chains are idle for lack of input, which have output piling up
unsold, and anything worth a decision this session.}}
