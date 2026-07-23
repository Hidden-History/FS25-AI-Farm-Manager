---
class: register
load: C
owns: "this farm's owned fleet + buildings/storage — durable purchase facts, not live wear/fuel"
cap_lines: 200
cap_kb: 20
rotation_trigger: on-resolve
archive_target: "history/archive/equipment-roster-archive.md"
resolved_markers: ["SOLD", "REMOVED"]
reconciliation: "sold/removed rows MOVE to archive (never blind row-shed); split by category if the ACTIVE set exceeds cap"
format_version: 2
parity_spec:
  required_sections: ["## The fleet", "## Buildings & storage", "## Condition", "## Reading of it"]
---

# Equipment Roster

_Snapshot: {{DATE}} ({{onboarding | updated at session N}}, in-game day {{DAY}}).
Source: `vehicles.xml`, entries filtered to this farm's `farm_id` from
`config.json`._

**Always report owned vs. total seen.** `vehicles.xml` (and `placeables.xml` for
buildings/storage) lists every machine and structure on the whole map, most of
which belong to other farms, map furniture, or NPC props -- not this one. State
both numbers explicitly, e.g. "vehicles.xml has {{N}} entries; {{M}} carry
`farmId="{{FARM_ID}}"` and are ours; the rest are the map's." Reporting only the
owned count without the total silently implies the parser filtered correctly --
say the total too, so a wrong filter is visible instead of invisible.

## The fleet

| Qty | Machine | Unit price | Line total | Role |
|---|---|---|---|---|
| {{N}} | {{MACHINE}} | {{PRICE}} | {{LINE_TOTAL}} | {{ROLE — what it's for, or leave "unclear" rather than guessing}} |

If a total fleet cost is quoted, cross-check it against the save's own record
(`farms.xml`'s `newVehiclesCost` or equivalent) rather than trusting your own sum
-- state which one you're reporting and whether they agree.

## Buildings & storage

Buildings and storage placeables live in a **different file** (`placeables.xml`,
not `vehicles.xml`) and are easy to omit entirely if the roster only walks
vehicles. List them separately:

| Placeable | Price | Note |
|---|---|---|
| {{NAME}} | {{PRICE}} | {{e.g. purchase date, what it holds, current fill state}} |

## Condition

**Never report a condition field you didn't actually find.** A parser returning
`None` for wear, hours, or fuel because the field lives somewhere the parser
didn't look (e.g. nested under a child element instead of as an attribute) is a
**parser miss**, not evidence the machine is unused -- and reporting it as "0
hours, never driven" turns a parser bug into a false claim about the fleet. Before
writing any condition line:

1. Confirm the field actually resolved to a real value (not a default, not a
   silently-caught exception).
2. Convert units before reporting anything -- wear/operating-time/fuel fields in
   FS25 saves are not reliably in the unit their name implies (seconds vs.
   minutes vs. hours all show up across different fields). Sanity-check against
   a real-world rate (e.g. implied fuel burn in L/h) before trusting a raw number.
3. If a field is genuinely absent or unreadable, write **"unknown"** and say why
   -- don't default it to zero and don't infer age/condition from a machine's
   filename or role (a name can be wrong).

| Metric | Range across the fleet | Source / confidence | Last confirmed |
|---|---|---|---|
| Operating time | {{RANGE, converted to a human unit}} | {{field name + unit conversion applied}} | {{DATE}} |
| Wear / damage | {{RANGE}} | {{field name}} | {{DATE}} |
| Age | {{VALUE}} | {{field name}} | {{DATE}} |
| Fuel | {{RANGE or spot examples}} | {{field name}} | {{DATE}} |

Operating time, wear, age, and fuel are **live** — `read_vehicles.py` answers them fresh every
session, and this file is only touched when equipment is bought/sold/repaired, so a Condition
row can sit unrevised while the real numbers drift (the F-117 stale-but-confident shape). **A
Condition row without its own `Last confirmed` date is not this session's answer** — re-run
`read_vehicles.py` before trusting a number here that's more than a session or two old.

## Reading of it

{{A paragraph of judgment, not just data: what the fleet is good at, what's
missing (e.g. "harvest-only, no seeder/tillage/sprayer"), and what that implies
for buy/sell decisions. Log any candidate purchases or sales in
`state/equipment-shopping-list.md` rather than deciding them here.}}
