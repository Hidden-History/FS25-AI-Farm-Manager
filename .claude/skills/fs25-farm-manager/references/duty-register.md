---
name: duty-register
description: 'The 16 duties S4 iterates as data. Adding a duty adds a row here, never a step or a file (DESIGN § 4.1).'
---

# Duty register

**This is data, not a workflow step.** S4 (`session-steps/s4-evaluate-duties.md`) iterates
these 16 rows against the current state view and emits each duty's structured output.
Everything here is DERIVED from `DUTY-MAP-farm-manager-2026-08-06.md` (the Duty Map, source of
record — re-derive from it, never from a paraphrase, if this file and the Duty Map ever
disagree) and from `PLAN-FARM-MANAGER-SKILL-ASSEMBLY-2026-08-09.md` § 7 (which corrected 12 of
16 `empty_means` cells that had gone un-copied, not un-traceable — see § 7.3's correction
banner there before assuming a gap here is real).

## Contract every row honours (§ 7.4, carried from Duty Map § 5.1 / DEC-069)

1. Every row's output carries a `status` field.
2. Every row states, in `empty_means`, what an empty or zero result actually means — never a
   bare empty list or a bare zero with no distinction from "unread."
3. The output schema is primary; any rendering (card, board column, future UI) is a
   **consumer** of the schema, never its author (DEC-069).

## The three degradation axes every row carries (§ 7.2)

| Axis | What it tests | How it's filled below |
|---|---|---|
| **1 · no fields / no animals / no productions** | The farm genuinely has none of what this duty needs | `degradation.axis1`, from the Duty Map's own "Degrades to" cell, per duty |
| **2 · parser failure** | The reader that feeds this duty could not run at all | `degradation.axis2` — **uniform across every row**: `status: unavailable` plus the reader's own `error` string, surfaced, never swallowed (§ 2.4: all 24 readers emit `error` on hard failure) |
| **3 · partial row unreadable** | Some but not all of what this duty needs came back readable | `degradation.axis3`, per duty, quoted from the Duty Map where it names one explicitly. Where the Duty Map names no partial-row case for a duty, this says so rather than inventing one — **absence of a named case is reported, not filled with a guess** |

---

## D-01 · Know the cash position and whether the farm is solvent

- **output_schema**: `{cash, loan, net_position, daily_ledger[5][33], lifetime{revenue, expenses, play_time}, status}`
- **target**: "Position" card, always column 1
- **empty_means**: a farm cannot have "no cash figure" — a missing value is `status: unavailable`, never `$0`
- **availability**: available now — cash, loan, the 5×33 ledger, and the 47-counter lifetime block. `read_farm_ledger.py` declares `capability_ids=["b39"]` and `capability_ids=["b40"]`, emitting `finance_ledger` and `lifetime_statistics`
- **capability trace**: a1, a2, b39, b40 (all available now)
- **degradation.axis1**: unchanged — cash, loan and the ledger exist on every farm regardless of animals or productions; this duty is the floor
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: not named in the Duty Map for this duty

## D-02 · Decide what to plant, where, and when

- **output_schema**: `{proposals: [{field_id, crop, rationale, window_period, expected_litres, expected_revenue, confidence}], escalate: true}`
- **target**: "Crop plan" board column, always flagged for owner decision (DEC-068 output contract)
- **escalate**: `true`
- **empty_means**: zero proposals when every owned field already carries a crop is a real answer — render as "all N fields committed," never as an empty board
- **availability**: available now (field state, ownership, prices, seed rates) · buildable (per-crop planting calendar, yield table)
- **capability trace**: a6, a8, a12, a13, a14, a34 (available now) · b32, b33, b34 (buildable)
- **degradation.axis1**: degrades **by construction**, not by branching — the rule is "plant to meet real demand"; with no productions and no livestock, internal demand is zero, so the identical rule resolves to "plant for market sale," ranked by price peak/trough. No special case to build.
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: not named in the Duty Map for this duty

## D-03 · Say what is ready to harvest right now

- **output_schema**: `{ready: [{field_id, crop, growth_state}], cut: [...], dead: [...], unknown: [{field_id, why}], status}`
- **target**: "Act today" card, top
- **empty_means**: `unknown` carries a per-field reason; "no fields ready" must render **visibly differently** from "readiness could not be determined" ([[RSK-001]] at the presentation layer)
- **availability**: available now
- **capability trace**: a6, a9, a10 (available now) · b32 (buildable)
- **degradation.axis1**: unchanged — a farm with no animals and no factories still harvests. On a farm with **no fields**, yields `status: unknown_by_design` with `empty_means: "you own no fields"`.
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: per-field `unknown_crop_state_on_owned_land` with its own reason, distinct from a genuine "no fields ready" — this is the row-level case [[RSK-001]] names; render each unknown field with its reason, never folded into "nothing ready"

## D-04 · Keep the soil right — lime, fertiliser, weeds, plough, roller

- **output_schema**: `{field_work: [{field_id, operation, urgency, input_fill_type, litres_required, cost}], status}`
- **target**: "Field work" board column
- **empty_means**: "no field work outstanding" — distinct from "soil state unreadable"
- **availability**: available now (field state, difficulty settings) · buildable (per-crop requirements, per-second spray rates, ground-type value map)
- **capability trace**: a6, a7, a33, a34 (available now) · b34, b36, b37 (buildable)
- **degradation.axis1**: unchanged — purely agronomic, no dependency on livestock or productions
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: not named in the Duty Map for this duty

## D-05 · Buy inputs when they are cheap

- **output_schema**: `{input_timing: [{fill_type, price_now, trough_period, peak_period, verdict: "buy"|"wait", saving_per_1000l}], current_period, status}`
- **target**: "Buy / wait" card
- **empty_means**: "no input purchase indicated"
- **availability**: available now
- **capability trace**: a12, a13, a14, a34 (available now)
- **degradation.axis1**: unchanged — every farm buys seed and fuel; narrows to fewer fillTypes on a simple farm, the rule is identical
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: not named in the Duty Map for this duty

## D-06 · Sell output at the right price, in the right place

- **output_schema**: `{sell_recommendations: [{fill_type, litres, location, best_station, price_now, peak_period, verdict}], status}`
- **target**: "Sell / hold" card
- **empty_means**: `all_stations_untraded: true` means "no station has traded yet, so station-level guidance is unavailable" — **must not render as "no opportunities"**
- **availability**: available now
- **capability trace**: a13, a15, a16, a17, a18, a34 (available now)
- **degradation.axis1**: unchanged, and this is the duty a minimal farm leans on hardest — with no productions, everything harvested is sold raw, so D-06 carries the whole revenue side
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: `all_stations_untraded: true` is itself a row-level partial case — a station with no trade history is not "no opportunity," it is "no guidance yet for this station specifically"; render per-station, not folded into a farm-wide null

## D-07 · Keep the livestock fed — the degraded duty

- **output_schema**: `{husbandries: [{id, animal_type, subtypes: [{sub_type, num, age, health, reproduction}], food_level_litres, food_capacity, production_factor, global_production_factor, days_remaining: null, days_remaining_status: "unknown_by_design", days_remaining_reason: "per-animal feed rate is sealed in dataS.gar (c4); accumulate N snapshots"}], status}`
- **target**: "Livestock" card
- **empty_means**: "you own no livestock" (Degrades-to row) — and `days_remaining` **must ship as an explicit null with its reason attached, never omitted, never estimated**. An omitted key reads as "fine"; that is the DEC-001 failure mode at the presentation layer.
- **availability**: `available now`: b10 (`read_livestock.py`, declares `capability_ids=["b10"]`, emits `animal_clusters`) and b13 (`read_farmland_areas.py`, declares `capability_ids` including `"b13"`; its relevance to *this* duty is the Duty Map's own categorization). Still `buildable`: b11, b12, b15, b16, b17 (no script declares these). `out of reach`: the forecast rate itself (bucket c4, sealed in `dataS.gar`) — the duty is admissible on the shipped/buildable inputs; the forecast half is not
- **capability trace**: b10, b13 (available now) · b11, b12, b15, b16, b17 (buildable) · rate is c4, out of reach — [[OOR-1]]
- **degradation.axis1**: no animals → `status: unknown_by_design`, `empty_means: "you own no livestock"`. Fully absent, cleanly — `read_placeables.py` already distinguishes empty-and-confirmed from unreadable.
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: `days_remaining` is a per-husbandry field that must ALWAYS be null with a reason today (the forecast is out of reach for every husbandry, not selectively) — this is not a partial case that varies row to row, it is a standing, structural null across the whole duty until the delta log exists

## D-08 · Manage the herd — condition, breeding, capacity

- **output_schema**: `{herd: [{husbandry_id, subtype, count, mean_age, mean_health, reproduction, capacity, utilisation_pct, verdict}], status}`
- **target**: "Livestock" card, second block
- **empty_means**: "you own no livestock" — distinct from "husbandry present but cluster data unreadable"
- **availability**: `available now`: b10 (`read_livestock.py`, `animal_clusters` — count, age, health, reproduction per cluster, this duty's core inputs), b39, b40 (`read_farm_ledger.py`). Still `buildable`: b12, b16, b17 (no script declares these)
- **capability trace**: b10, b39, b40 (available now) · b12, b16, b17 (buildable)
- **degradation.axis1**: no animals → `status: unknown_by_design`, `empty_means: "you own no livestock"`
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: "husbandry present but cluster data unreadable" is named explicitly as distinct from "no livestock" — render per-husbandry, never collapse an unreadable cluster into "none owned"

## D-09 · Run the production lines — throughput, starvation, backpressure

- **output_schema**: `{lines: [{placeable, production_id, enabled, cycles_per_hour, inputs: [{fill_type, per_cycle, level, hours_to_empty}], outputs: [{fill_type, per_cycle, level, capacity, hours_to_full}], cost_per_active_hour, verdict}], status}`
- **target**: "Productions" card
- **empty_means**: "no line needs attention" ≠ "recipe graph unresolved"
- **availability**: `available now`: storage contents/ownership (a17, a18, a21, a22), the recipe graph and capacity ceilings (`read_production_defs.py`, `capability_ids` including b1, b2, b7, b8), and the factory throughput half (`read_productions.py`, `capability_ids` including b3, b4, b5, b6, b9, emits `production_lines`). § 0.1's "the join is deterministic and nothing computes it yet" no longer holds — something now computes it.
- **capability trace**: a17, a18, a21, a22, b1, b2, b3, b7, b8 (all available now)
- **degradation.axis1**: no productions → `status: unknown_by_design`, `empty_means: "you own no production points"`. Clean absence — D-02's "plant for demand" correctly collapses to "plant for sale" in the same breath.
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: `hours_to_empty`/`hours_to_full` are real, deterministic numbers per line (§ 0.1) — unlike D-07, this duty has no sealed rate, so a per-line gap here is a genuine parser/recipe-join failure (axis 2), not a structural partial case

## D-10 · Collect the money the factories are holding

- **output_schema**: `{unclaimed_total, by_placeable: [{placeable, amount}], status}`
- **target**: "Position" card, liabilities line
- **empty_means**: a genuine `0.00` and an unread file must render differently — the amounts are fractions of a dollar, so a swallowed error looks exactly like a true zero
- **availability**: `available now` — `read_productions.py` declares `capability_ids=["b4"]`; its `production_costs_to_claim` section reports per-placeable `costs_to_claim` and distinguishes an absent attribute from a genuine zero, matching this duty's own concern in `empty_means`
- **capability trace**: b4 (available now)
- **degradation.axis1**: no productions → the attribute does not occur at all; `status: unknown_by_design`, `empty_means: "you own no production points"`
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: the true/false-zero distinction above IS the axis-3 case for this duty — a `0.00` total must be distinguishable from a total that could not be summed because one placeable's attribute was unreadable

## D-11 · Know what is in store and whether it is about to overflow

- **output_schema**: `{stored: [{fill_type, total_litres, locations: [{where, litres, capacity, pct_full}]}], bunker_silos, object_storage, status}`
- **target**: "Storage" card
- **empty_means**: "confirmed empty" — explicitly not "unreadable"; the parser already draws that line and the renderer must preserve it
- **availability**: `available now`: contents/ownership (a17, a18, a19, a20), the capacity ceiling (b7, `read_production_defs.py`'s `storage_capacities` section), and object/bale storage (b22, `read_bales_pallets.py`, `capability_ids` including b22, emits `object_storage_bales`). A "silo full" alert is computable — the join of `read_placeables.py`'s level against `read_production_defs.py`'s ceiling belongs to whatever consumes both, per § 0.1's own note, but neither half is missing.
- **capability trace**: a17, a18, a19, a20, b7, b22 (all available now)
- **degradation.axis1**: unchanged — every farm stores something; a farm storing nothing yields a confirmed-empty result, not an error
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: not named in the Duty Map for this duty (the confirmed-empty-vs-unreadable distinction is a parser-boundary property, already covered by axis 2)

## D-12 · Keep the fleet able to work

- **output_schema**: `{fleet: [{unique_id, name, damage, damage_status, fuel_level, operating_time, verdict}], unreadable_count, status}`
- **target**: "Fleet" card
- **empty_means**: 34 of 128 vehicles have no readable damage figure today — those must render as "condition unknown," never as "condition fine" (the DEC-001 rule applied to a per-row gap)
- **availability**: available now
- **capability trace**: a25, a26, a27, a28 (available now)
- **degradation.axis1**: unchanged — every farm has machines
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: per-vehicle damage may be individually unreadable while the rest of the fleet reads fine — each such vehicle renders `damage_status: "condition unknown"` and is counted in `unreadable_count`, never silently reported as undamaged

## D-13 · Plan fleet capital — buy, sell, lease, replace

- **output_schema**: `{fleet_value, candidates_for_replacement: [...], market_listings: [{item, listed_price, new_price, time_left, verdict}], escalate: true, status}`
- **target**: "Capital" board column, owner decision
- **escalate**: `true`
- **empty_means**: an expired-listing set is "nothing on the market right now"; the 1 unresolved listing must appear with its error, not be silently dropped from a count of 4
- **availability**: `available now`: valuation/listings (a1, a2, a25, a26, a29, a32), the running-cost ledger (b39, `read_farm_ledger.py`), and per-vehicle configuration detail (b41, `read_fleet.py`, declares `capability_ids=["b18","b41"]`, emits `vehicle_configurations`)
- **capability trace**: a1, a2, a25, a26, a29, a32, b39, b41 (all available now)
- **degradation.axis1**: unchanged
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: a listing that failed to resolve carries its own `resolve_error` and must still appear in `market_listings`, counted separately from the resolved set — never dropped from the total

## D-14 · Choose which contracts to take

- **output_schema**: `{contracts: [{unique_id, type, field_id, reward, reward_note, days_left, verdict}], status}`
- **target**: "Contracts" board column
- **empty_means**: For an unaccepted/unresolved mission, `read_missions.py` emits `reward: null` (not `0`) plus a `reward_note` explaining it's computed at accept-time and must never be reported as `$0` (F-025) — the raw value is preserved separately as `reward_raw`. The literal string `"<raw> <- PLACEHOLDER, NOT A PAYOUT..."` is written into the **`info.reward`** sub-field, not the top-level `reward` key — it exists to catch a reader who reaches into the raw `info` dump instead of the corrected top-level field. Build against `reward` + `reward_note`, never against `info.reward`, and never wait for a `0` sentinel — it never arrives
- **availability**: available now
- **capability trace**: a11, a30, a31 (available now) · b39, b40 (available now — `read_farm_ledger.py` ships both; re-verify before relying further)
- **degradation.axis1**: unchanged — contracts exist independently of animals and productions, and are the main income route on a minimal farm
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: an unresolved reward (`reward: null`, `reward_note` present) is the per-row partial case for this duty — a contract whose true reward is not yet known must never render as a real `$0`, and a renderer must read `reward`/`reward_note`, never `info.reward`

## D-15 · Schedule work around the weather

- **output_schema**: `{now: {...}, forecast: [{type, start_day, start_clock, duration_hours, minTemperature, maxTemperature}], hazards: [...], ground_wetness, status}`
- **target**: "Week ahead" card
- **empty_means**: `read_weather.py`'s `forecast_temperature` section ships real values, keyed `minTemperature`/`maxTemperature` (not `min_temp`/`max_temp`), when its `status` is `"ok"` — quoted from a real run: `{"minTemperature": "18", "maxTemperature": "27", ...}` under `data`. **Never render `unknown_by_design` for temperature when this section's `status` is `"ok"`** — that overwrites a real read with a designed absence. If `forecast_temperature.status` is `"unavailable"` (the map-config join could not resolve — e.g. no install/mods dir configured), report `minTemperature`/`maxTemperature: null` with the reader's own `reason` string carried through, never `unknown_by_design` as a substitute for reading the actual status the script reports
- **availability**: `available now`: current weather, 5-slot forecast (a9, a10, a11), temperature via the b26 join, and storm/hazard events (b29, b30, b31) — `read_weather.py` declares `capability_ids` including b26, b29, b30, b31. Still `buildable`: the full 30-slot forecast queue beyond the first 5, ground wetness rendering
- **capability trace**: a9, a10, a11, b26, b29, b30, b31 (all available now)
- **degradation.axis1**: unchanged — weather is universal
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: temperature is null only when the map-config join genuinely cannot resolve (unresolvable install/mods paths, or — per `read_weather.py`'s own `⚖ RULED READING` caveat — the `(season, typeName, variationIndex)` join itself is asserted rather than documented, so a future falsification of that join is the real remaining risk, not a missing capability). This is not D-07's permanent-null shape — check `forecast_temperature.status` per run rather than assuming null.

## D-16 · Decide whether to buy land

- **output_schema**: `{owned_parcels, owned_area_ha, candidates: [{parcel_id, area_ha, cost, npc_owner, affordability}], cost_reconciliation_status, escalate: true, status}`
- **target**: "Capital" board column, owner decision
- **escalate**: `true`
- **empty_means**: `field_purchase_cross_check` is **permanently `None`** — `read_farmland_areas.py:242` sets `CROSS_CHECK_ENABLED = False`, so the field is never emitted. `references/blocked-capabilities.json`'s `land_value` entry (the single authority, § 9.4) states the underlying figures never disagreed (sum of five slots = 39,432,192.00 = `computed_owned_total_cost`, to the cent) — the apparent "tens of millions" gap was the `find`-vs-`findall` bug (BUG-014), slot-0-only (10,223,376) against the full sum. `field_purchase_cross_check: null` is the **permanent, structural** state, not a per-session unknown — never render a comparison for it, and never treat its `None`-ness as a finding to escalate
- **availability**: available now (owned parcels, area, cost, candidates) — `cost_reconciliation_status` is **not available and not buildable**: the comparison it would report is blocked (BUG-014) and would show no disagreement even if unblocked (see `empty_means`). Omit it or render `status: "blocked_by land_value (BUG-014)"`, never a computed comparison
- **capability trace**: a1, a2, a3, a4, a5, b39 (all available now — `read_farm_ledger.py` ships b39)
- **degradation.axis1**: unchanged — land exists on every farm
- **degradation.axis2**: uniform (see contract above)
- **degradation.axis3**: a `blocked_by` marker on the land-value figure (§ 9.4, `blocked-capabilities.json`, `land_value`/BUG-014) must be surfaced distinctly if it ever appears in a row — a block is a different claim from a comparison, and neither is a live disagreement today

---

## Provenance

Every field above traces to `DUTY-MAP-farm-manager-2026-08-06.md`'s per-duty `Output`,
`Availability`, `Degrades to` and `Capability ids` rows, or to
`PLAN-FARM-MANAGER-SKILL-ASSEMBLY-2026-08-09.md` § 7.3's corrected `empty_means` column. Neither
document is restated here in full — re-derive from them, not from this summary, if a duty's
exact wording matters for a dispute. `escalate: true` is carried verbatim from each duty's own
`output_schema` (D-02, D-13, D-16 only) per DEC-068's output contract, and feeds S5's
DECIDED/ESCALATED split directly.
