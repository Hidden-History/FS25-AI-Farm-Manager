---
class: register
load: C
owns: "the durable index of this farm's owned animal buildings — not their live counts/fill"
cap_lines: 80
cap_kb: 8
rotation_trigger: on-resolve
archive_target: "history/archive/husbandry-roster-archive.md"
reconciliation: "sold/removed buildings MOVE to archive (never blind row-shed); Count is live, Last updated is its confirm-date"
format_version: 1
parity_spec:
  required_sections: ["## Buildings owned", "## Reading of it"]
---

# Animal Husbandry Roster

_Snapshot: {{DATE}} ({{onboarding | updated at session N}}). Source:
`placeables.xml` husbandry buildings filtered to this farm's `farm_id`._

**If this farm owns no animal buildings, say so explicitly and stop there --
don't leave the file looking unpopulated.** "0 husbandry buildings owned as of
{{DATE}}" is a complete, correct, useful entry. A blank file with no snapshot
date is indistinguishable from "never checked," which is a worse state than
"checked, owns none." Update the snapshot date whenever this is re-verified,
even if the answer is still zero.

## Buildings owned

_(Leave this section as "none" if it's true -- don't delete the section
heading.)_

| Building | Animal type | Count | Last updated |
|---|---|---|---|
| {{BUILDING_NAME_OR_ID}} | {{ANIMAL_TYPE}} | {{NUM_ANIMALS}} | {{DATE}} |

**`Count` is live** — `read_placeables.py` answers it fresh every session. `Last updated` is its
confirm-date, not decoration: don't trust a `Count` older than the current session without
re-checking. The durable content here is the *list of buildings owned* (the index); the count
lives in the save. When a building is sold or removed, MOVE its row to
`history/archive/husbandry-roster-archive.md` — never blind-delete.

For each building above with animals in it, keep a matching dossier (created
from `templates/husbandry-dossier.md`) covering health, feed/water/straw levels, and
output accumulated -- this roster is the index, the dossier is the detail.
`sanctum/state/husbandry-dossiers/` is pre-created by `init_sanctum.py`
alongside `state/field-dossiers/` and `history/journal/` -- add a dossier
file the first time one is needed, the same way `state/field-dossiers/` is
populated on demand.

## Reading of it

{{If none owned: is this deliberate (the farm doesn't do livestock) or an open
question worth a directive (e.g. "decide whether to add a husbandry chain")? If
owned: overall health/output picture and anything that needs attention this
session -- feed running low, output ready to sell, a building underused.}}
