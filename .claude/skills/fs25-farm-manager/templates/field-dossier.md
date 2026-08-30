---
class: dossier
load: C
owns: "one field's durable quirks, yield history, and event log — never its live crop/ground state"
cap_lines: 120
cap_kb: 12
rotation_trigger: on-cap-relocate
archive_target: "state/field-dossiers/field-{id}-history.md"
reconciliation: "no live-state figure is stored here; History is append-only, oldest rows relocate losslessly on cap"
format_version: 1
parity_spec:
  required_sections: ["## Read live — don't trust a cached figure here", "## Durable facts (the reason this file exists)", "## History", "## Notes / quirks"]
---

# Field {{FIELD_ID}}

**Size / notes:** {{SIZE_OR_MAP_NOTES — durable; a field's size only changes on a plow-merge, which is itself a History entry}}
**Last ownership re-verified:** {{DATE — dates the anchor so a session knows whether "we own this" is this morning's fact or three sessions old (F-106); the ownership list itself lives in config.json, not here}}

## Read live — don't trust a cached figure here

Crop, growth state, ground type, weeds, lime/spray/water levels — all of it changes between
sessions and all of it is answered authoritatively by `read_fields.py` / `farm_snapshot.py`
every session. This file does **not** carry those numbers: a cached copy goes stale the moment
it's written and reads as current when it isn't (friction-log F-117 read `HARVEST_READY` on two
already-harvested fields; F-106 nearly missed a land purchase off a stale count). If you find a
"current state" figure written into this file, treat it as an error in the file, not this
session's answer.

## Durable facts (the reason this file exists)

{{Quirks, constraints, and history the save genuinely does NOT restate every session — e.g.
"this field floods every autumn," "best yield so far was maize at N," "crop calendar is
map-overridden here — confirmed against the map's foliage XML, see state/crop-grace-periods.md." A
durable fact is something you learned by watching THIS field over time, not something in this
session's snapshot. If you're inferring from a general FS25 pattern rather than this field's own
history, write "expected, unconfirmed on this field" rather than stating it as fact.}}

## History

Append-only log of what actually happened — planted, harvested, fertilized, sold yield, etc.
An exact yield figure or a specific fertilize date may matter later, so never summarize a row.

| Date | Event |
|---|---|
| {{DATE}} | {{EVENT — planted, harvested, fertilized, sold yield, etc.}} |

_When this file would exceed its cap, move the **oldest** History rows verbatim into
`state/field-dossiers/field-{{FIELD_ID}}-history.md` (uncapped) and leave a one-line pointer here
(`Full history: field-{{FIELD_ID}}-history.md — N events before {{DATE}}`), keeping the most
recent ~10–15 rows live. Lossless move, never a summary._

## Notes / quirks

{{ANYTHING_WORTH_REMEMBERING that isn't a dated event — durable by construction.}}
