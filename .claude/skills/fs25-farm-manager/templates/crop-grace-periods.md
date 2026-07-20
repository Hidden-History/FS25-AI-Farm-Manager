---
class: dossier
load: C
owns: "this map/engine's harvest-ready spoilage grace periods and tick-timing — one-time-derived, stable until map/mods change"
cap_lines: 100
cap_kb: 10
rotation_trigger: none
archive_target: N/A
reconciliation: "a row means this map's foliage XML or an empirical test was actually checked; unchecked crops stay in 'Not yet checked', never guessed"
format_version: 1
parity_spec:
  required_sections: ["## Engine tick-timing", "## Per-crop grace periods observed on THIS map"]
---

# Crop grace periods & engine-timing facts (this farm/map)

_Durable, one-time-derived facts about how THIS save's active map/engine handles harvest-ready
spoilage — expensive to derive (read foliage XML growth rules, or run an empirical
one-day-advance test), genuinely stable until the map/mods change. Base-game per-crop
planting/harvest windows already live in `references/game-guide/crops.md` — don't duplicate that
table here; this file is specifically about grace periods and the tick-timing question
`references/crop-calendar.md` flags as open. **Starts empty on a new farm — that's the honest
state, not a design gap.**_

## Engine tick-timing

_Resolve ONCE per save (per `references/crop-calendar.md`) — it's a property of the engine, not of
any one field._

**Status:** {{unresolved | resolved on {{DATE}}}}
**Test:** advance the clock exactly one in-game day, diff `growthState` before/after.
**Result:** {{"today's tick already applied" | "today's tick still pending"}} — {{evidence: the
exact before/after growthState values observed}}.

_Until resolved, treat any exact day-count-to-spoilage as provisional and use the conservative
reading (assume less grace, not more)._

## Per-crop grace periods observed on THIS map

_Only what's been checked — not a base-game default. Grace periods don't generalize even within
one crop category on the same map (`references/crop-calendar.md`)._

| Crop | Grace period (ticks/days) | Base game or map-override? | Source | Last verified |
|---|---|---|---|---|
| {{CROP}} | {{N ticks, or "none — spoils next tick"}} | {{base \| map override: <map name>}} | {{foliage XML path checked, or empirical observation}} | {{DATE}} |

**Not yet checked:** {{list crops this farm grows that haven't had their grace period confirmed —
treat as unknown. Before recommending a fast-forward or sleep past a `HARVEST_READY` field, THIS
file (not memory, not a base-game assumption) answers whether that's safe; if the crop isn't in
the table yet, treat it as zero grace (fail safe) rather than assuming there's time (F-117).}}
