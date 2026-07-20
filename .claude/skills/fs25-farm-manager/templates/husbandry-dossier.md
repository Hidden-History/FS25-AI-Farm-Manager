---
class: dossier
load: C
owns: "one animal building's durable quirks, consumption/price patterns, and event log — never its live fill/health state"
cap_lines: 100
cap_kb: 10
rotation_trigger: on-cap-relocate
archive_target: "state/husbandry-dossiers/husbandry-{id}-history.md"
reconciliation: "no live-state figure is stored here; History is append-only, oldest rows relocate losslessly on cap"
format_version: 1
parity_spec:
  required_sections: ["## Read live — don't trust a cached figure here", "## Durable facts (the reason this file exists)", "## History", "## Notes / quirks"]
---

# Husbandry: {{BUILDING_NAME_OR_ID}}

**Animal type:** {{ANIMAL_TYPE — durable; a building's type doesn't change without a rebuild event}}

## Read live — don't trust a cached figure here

Animal count, health/productivity, feed/water/straw levels, output accumulated — all of it
changes between sessions and is answered authoritatively by `read_placeables.py` /
`farm_snapshot.py` every session. This file does **not** carry those numbers: a cached copy goes
stale the moment it's written and reads as current when it isn't (friction-log F-117, F-106). A
"current state" figure written here is an error in the file, not this session's answer.

## Durable facts (the reason this file exists)

{{Feed supplier, a consumption rate you've actually watched drop over sessions, an output
sell-price pattern you've observed — genuinely durable, not this session's fill levels. Cross-check
any feed/product claim against `references/game-guide/animals.md`'s manual table before writing it
as a farm-specific quirk: if the manual already states it generally, it doesn't belong here as if
this farm discovered it.}}

## History

Append-only log of what actually happened — bought animals, sold output, ran low on feed,
illness, etc. Never summarize a row; an exact figure or date may matter later.

| Date | Event |
|---|---|
| {{DATE}} | {{EVENT — bought animals, sold output, ran low on feed, illness, etc.}} |

_When this file would exceed its cap, move the **oldest** History rows verbatim into
`state/husbandry-dossiers/husbandry-{{BUILDING_NAME_OR_ID}}-history.md` (uncapped) and leave a
one-line pointer here, keeping the most recent rows live. Lossless move, never a summary._

## Notes / quirks

{{ANYTHING_WORTH_REMEMBERING that isn't a dated event — durable by construction.}}
