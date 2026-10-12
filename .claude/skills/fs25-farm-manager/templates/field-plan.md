---
class: register
load: C
owns: "the player-reviewed plan of the next crop for each owned field — only what the save cannot say; never a field's live crop or harvest date"
cap_lines: 200
cap_kb: 24
rotation_trigger: none
archive_target: N/A
reconciliation: "one row per canonical field id (a merged field is ONE row, keyed by the id the merge table reports); rows are written only by scripts/record_field_plan.py; a changed plan resets Reviewed to no"
format_version: 1
parity_spec:
  required_sections: ["## Plan rows"]
---

# Field plan

The per-field crop plan the manager keeps current and reviews with the player. Format contract:
`references/field-plan-format.md`. **Do not edit the table by hand** — write it with
`scripts/record_field_plan.py`, which checks every field id against the save and refuses a
malformed row. The FIELDS tab reads this file (through `emit_fields_xml.py`) and shows each row.

**Current crop and harvest-by are NOT stored here** — they change every session and are read live
from the save. A field with no row has no next crop planned: that is a gap to report, not a blank
to leave.

## Plan rows

| Field | Next crop | Plant window | Planned on | Reviewed |
|---|---|---|---|---|
