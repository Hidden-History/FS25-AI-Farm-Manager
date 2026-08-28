# Crop Calendar Reference

**Important caveat before using this:** planting/harvest windows in Farming
Simulator depend on the map and on whether a real-seasons system is active
(vanilla FS25 has a season/year cycle; maps and mods commonly adjust growth
speed, available crops, or windows further — see below, this isn't rare).
Treat the seasonal pattern and crop groupings below as a *starting prior*,
not ground truth for any specific farm. The authoritative source is always
`fields.xml`'s `growthState` / `groundType` values from `read_fields.py` — if
what you observe in the save disagrees with this reference, trust the save
and update your working assumptions accordingly (note the discrepancy in the
field's dossier).

## The growth model, underneath the seasonal-pattern table

The table below is a human-readable summary. What the game actually tracks
is more precise, and worth understanding because it's what lets a briefing
say something sharper than "harvest season is coming":

- Each crop's real state is `fields.xml`'s `growthState` — a small integer.
  It is the crop's current position (1-indexed) in an ordered list of
  `<foliageState>` elements defined in that crop's own foliage XML
  (game install `data/foliage/<crop>/<crop>.xml`, or a map/mod's override —
  see below). **`growthState` (via `read_fields.py`'s `crop_state`) is the
  reliable readiness signal — not `groundType`**, which is the terrain
  texture: it stays `HARVEST_READY` on a field cut days ago, because the
  texture isn't repainted when the crop comes off. Use `growthState` for
  everything — whether a crop is ready, how far along a growing crop is, or
  how long a harvest-ready crop has been sitting.
- **Do not trust that file's human-readable comment tables** (the
  `1 0 0 0 - invisible`-style lines that precede the state list in most
  foliage XMLs). At least one crop's comment table was found stale — missing
  a state that exists in the real element list, which shifted every
  downstream number by one and pointed at the wrong state name entirely.
  Parse the actual `<foliageState>` elements in document order; never the
  comments describing them. This is the same lesson as
  `reading-the-save.md`'s "verified by running" rule, applied to comments
  instead of docstrings — a comment is a claim, the elements are the fact.
- Advancement is period-based, not continuous: each crop's `<growth>
  <seasonal>` block defines 12 named periods (the standard
  `EARLY_SPRING … LATE_WINTER` cycle) each with `<update startState=".."
  endState=".."/>` rules. On each period tick, a field advances **exactly
  one state step** if a rule matches its current state that period;
  otherwise it sits still (dormant) until a matching period comes around
  again — which, for a crop caught behind its normal calendar, can mean
  "not until next year," not "soon." A field sitting at an unexpectedly early
  stage very late in its season is more likely stalled-until-next-cycle than
  slow-but-progressing — don't assume steady linear progress without
  checking whether a rule for its current state exists in the *next*
  upcoming period.
- How many real or in-game days a period-tick costs is a `time-mechanics.md`
  question (`daysPerPeriod`), not a crop-calendar one — cross-reference it,
  don't re-derive it here. A low `daysPerPeriod` compresses this whole model
  hard: a "one period" growth step and a "one season" harvest window can
  become the same few in-game days.

## Maps commonly override growth calendars — check that before trusting base-game timing

A map or mod frequently ships its own growth calendars for some or all crops,
and where it does, its numbers are what actually governs the save — not the
base game's. This is common, not an edge case: on one save, the active map
overrode roughly half its registered crops' calendars, changing transition
timing and in at least one case adding harvest-ready self-loop rules the
base game didn't have (see Spoilage, below).

**Before quoting any crop's timing, check the active map's own fruit-type
registry first** (typically a `maps_fruitTypesNew.xml`-style file inside the
map's package, itself often a zip — read the zip member directly rather than
extracting to disk) to see which crops it overrides and where their foliage
XML actually lives. Fall back to the base game's `data/foliage/` copy only
for crops the map doesn't touch. Assuming base-game timing without checking
is exactly the kind of confident-but-wrong read this project exists to avoid.

A crop can also appear in `fields.xml` (a real, present field) while being
absent from the active map's fruit-type registry entirely — decorative or
leftover data the map doesn't actively manage. Falling back to the base
game's calendar for such a crop is a reasonable default, but flag it as
unconfirmed rather than asserting the map genuinely simulates it.

## Spoilage: harvest-ready is not a stable state

**This is the single biggest gap in treating "harvest window opens in
\[season\]" as the whole story.** A crop that reaches `HARVEST_READY` does
not wait indefinitely — most crops have a `harvestReady → dead` transition
rule sitting in some later period, and once that period ticks, an
unharvested crop degrades and the yield opportunity is gone. Whether that
happens in the very next period-tick or many periods later depends entirely
on whether the crop's calendar (base game or map override) includes a grace
period — a self-loop rule that lets it sit safely at `harvestReady` for
extra ticks before the `dead` transition can fire.

**Grace periods vary enormously, crop to crop, on the same map** — this is
not a property you can generalize from one crop to a whole category like
"grains." On one save, three grain crops spoiled in the very next period-tick
(no grace loop at all) while a fourth grain crop, under the same map's rules,
had a grace loop giving it roughly a full year's worth of periods before the
same fate. A briefing that treats "grain crops" as one bucket for urgency
purposes will be right about some of them and dangerously wrong about
others.

**Practical rule: before recommending any fast-forward or sleep past the
current moment (see `time-mechanics.md`), check every `HARVEST_READY` field's
grace period, not just its current readiness.** A player who fast-forwards or
sleeps past a no-grace-period crop's next tick loses that harvest with no
warning — and the manager's own advice would be what caused it. "Harvest
window opens in late summer" is true and also nearly useless if the window
closes one tick later.

## An open question about timing — do not resolve this by guessing

There is a genuine, unresolved ambiguity in reading a static save snapshot:
**has "today's" period tick already been applied to the `growthState` you're
reading, or is it still pending at the next day-rollover?** Both readings are
internally consistent with the same file contents, and they can disagree by
an order of magnitude on how much time a given field actually has —
"effectively no near-term risk" under one reading, "spoils tonight" under the
other, for the exact same observed state.

This cannot be resolved by reasoning about the files harder. It has a cheap,
definitive, one-time empirical answer: **note current `growthState` values,
advance the in-game clock by exactly one day (the smallest safe step),
re-read, and diff.** Whichever reading matches is the confirmed behavior for
this engine build, and it's a property of the engine — not of any one
field or save — so it only needs answering once. Until that test has been
run and recorded, treat any exact day-count to spoilage as provisional and
say so; do not assert a specific number as settled fact. When in doubt, use
the more conservative reading (assume less grace, not more) so a wrong guess
fails safe rather than costing a harvest.

## General seasonal behavior (season-level heuristics, not per-crop timing)

**For exact per-crop planting/harvest windows, use `game-guide/crops.md`'s data table** —
that's now precisely sourced from the official FS25 manual (all 26 base crops), so it's not
worth re-deriving or re-asserting crop-by-crop here. What follows is genuinely general
season-level behavior that table doesn't cover: what *kind* of field activity to expect each
season, independent of which specific crops a given farm grows.

| Season | Typical field activity |
|---|---|
| **Spring** | Main planting window opens for most crops; early-year fertilizing/liming |
| **Summer** | Growth continues for spring-planted crops; harvest-ready state begins appearing for the earliest-maturing ones — check spoilage grace period immediately, don't assume a leisurely window |
| **Autumn** | Main harvest window for most spring-planted crops; autumn-planted ("winter") crops' sowing window opens |
| **Winter** | Autumn-planted crops sit dormant/slow-growing; limited field work; good season for equipment maintenance and catching up on contracts |

Cross-reference `game-guide/crops.md` for which specific crops on this farm fall into
"earliest-maturing," "spring-planted," or "autumn-planted" this table's cells refer to — don't
substitute genre convention or memory for that lookup, and don't assume any of this timing
holds if the active map overrides growth calendars (see above).

## How to use this with live data

1. Cross-reference `currentSeason` from `read_environment.py` against a
   field's `fruitType`/`plannedFruit` and `growthState` from `read_fields.py`.
2. If a field is `FALLOW` and the season matches a normal planting window for
   a crop the player usually grows there (check the field's dossier
   history), proactively suggest planting rather than waiting to be asked.
3. Before quoting any timing number, check whether the active map overrides
   that crop's calendar (see above) — don't assume base-game defaults apply.
4. If `groundType` shows a field is `HARVEST_READY` (or the two-stage/
   multi-stage equivalents some crops use), treat spoilage risk as the
   immediate next question, not an afterthought — check that crop's grace
   period before suggesting the player wait, fast-forward, or sleep past it.
5. If `growthState` suggests a crop is still growing, decode its position via
   the crop's own `<foliageState>` list (never the comment table) to name the
   stage precisely, and project forward using the crop's `<seasonal>` rules —
   remembering the open tick-timing question above when stating an exact
   day-count.
6. If you notice a farm's actual behavior contradicts the general pattern
   above (e.g., maize growing through what should be winter, or a field
   stalled at an early stage long past its normal window), trust the save
   data, note the discrepancy in the field's dossier, and stop relying on
   this reference for that crop on that farm.
