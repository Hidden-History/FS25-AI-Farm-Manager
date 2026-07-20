---
class: dossier
load: C
owns: "one production chain's durable quirks, consumption/sell patterns, and event log — never its live fill/status state"
cap_lines: 100
cap_kb: 10
rotation_trigger: on-cap-relocate
archive_target: "state/production-dossiers/production-{id}-history.md"
reconciliation: "no live-state figure is stored here; History is append-only, oldest rows relocate losslessly on cap"
format_version: 1
parity_spec:
  required_sections: ["## Read live — don't trust a cached figure here", "## Durable facts (the reason this file exists)", "## History", "## Notes / quirks"]
---

# Production: {{BUILDING_NAME_OR_ID}}

**Type:** {{PRODUCTION_TYPE — dairy, sawmill, bakery, etc.; durable, a chain's type doesn't change without a rebuild}}

## Read live — don't trust a cached figure here

Input fill on hand, outputs accumulated, running/idle status, efficiency — all of it changes
between sessions and is answered authoritatively by `read_placeables.py` / `farm_snapshot.py`
every session. This file does **not** carry those numbers: a cached copy goes stale the moment
it's written and reads as current when it isn't (friction-log F-117, F-106). A "current state"
figure written here is an error in the file, not this session's answer.

## Durable facts (the reason this file exists)

{{Typical input consumption rate you've watched over sessions, the best sell point for this
output, a chain quirk (e.g. "stalls below 200L input, not at 0") — genuinely durable, not this
session's fill levels. Cross-check any input→output claim against
`references/game-guide/production.md`'s Production Overview table before writing it as a
farm-specific quirk: if the manual already states it generally, it doesn't belong here.}}

## History

Append-only log of what actually happened — ran out of input, sold output, upgraded, idle for
X days, etc. Never summarize a row; an exact figure or date may matter later.

| Date | Event |
|---|---|
| {{DATE}} | {{EVENT — ran out of input, sold output, upgraded, idle for X days}} |

_When this file would exceed its cap, move the **oldest** History rows verbatim into
`state/production-dossiers/production-{{BUILDING_NAME_OR_ID}}-history.md` (uncapped) and leave a
one-line pointer here, keeping the most recent rows live. Lossless move, never a summary._

## Notes / quirks

{{ANYTHING_WORTH_REMEMBERING that isn't a dated event — durable by construction.}}
