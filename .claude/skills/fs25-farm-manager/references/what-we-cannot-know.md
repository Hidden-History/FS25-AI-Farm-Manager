---
name: what-we-cannot-know
description: 'The short, deliberately short list of what genuinely cannot be read from disk — ask for these, and only these. Everything else is a read, not a question.'
---

# What we cannot know

## What the disk genuinely cannot answer

Short, and keeping it short is the point. Everything not on this list comes from the
save/install/mod files, never a question — asking for a number the disk holds is the mistake
that cost this farm real work. Asking is not the safe default: a question spends the
player's attention and implies the data is unavailable when it isn't.

1. **Contract rewards.** Field-tied contracts read `reward="0"` in `missions.xml` because the
   game computes the payout at accept-time, not when it's offered. `read_missions.py` emits
   `reward: null` + a `reward_note`, not a bare `0` — a `0` would be indistinguishable from
   "pays nothing." **Only the in-game contract screen has the number.** Ask, and log it.
2. **Their goals, risk appetite, and standing priorities.** Genuinely human — the doctrine
   interview in `references/workflow-onboarding.md`, which becomes `sanctum/identity/decision-making.md`.
3. **Whether they slept.** Sleep is a discontinuous jump in game time; it voids any reasoning
   that infers elapsed time from a `dayTime`/`playTime` ratio. Ask; never infer it.

**Conditionally derivable — not always answerable, but NOT human-only either:** the loan's
annual interest rate. The manual (p.8) says loan interest is paid once per month, billing
frequency verified; a year is always 12 months regardless of `daysPerPeriod`, so
`check_sanctum_freshness.py`'s `probe_interest_rate` derives it as one month's charged
`loanInterest` (from `farms.xml`'s `<stats>` finance ledger) × 12 / loan. The flat-monthly
amount that formula assumes is the standard convention and matches all current evidence, but
isn't yet empirically confirmed on a non-default calendar (`daysPerPeriod != 1`). It genuinely
can't answer yet if no loan is outstanding, or no month has charged interest — say so, don't
guess a rate. The in-game loan screen always has the current number if asked.

**Never ask for, because it's readable:** cash and loan (`read_economy.py`), owned parcel ids
(`read_economy.py`), **owned hectares and land cost** (`read_farmland_areas.py`), **which
fields are theirs** (`read_fields.py`) — resolves on any map via a spatial join against the
map's own field polygons, and reports coverage per save; a field it cannot resolve reads
`farmland_id: null` with a reason, never a guess (see `references/reading-the-save.md`'s
field-vs-parcel section) —
the fleet (`read_vehicles.py`), day/time/season/weather
(`read_environment.py`), map, difficulty, timeScale and autoSaveInterval (`read_career.py`),
the savegame location (`locate_save.py`), **store prices for anything not yet owned**
(`read_store_prices.py`), **what the farm is holding and what it's worth** — grain in vehicles
and silos (`farm_snapshot.py` → `inventory`), **what seed//fertilizer//lime//herbicide cost and
when they're cheapest** (`read_fill_prices.py`), **seed litres per hectare per crop**
(`read_game_defs.py`), or **what a used listing is actually worth** (`read_equipment_market.py`).

## On disk, but nowhere it can be found

A third case, and it is neither of the two above. The game install and the mods folder hold real, readable data — base-game store prices, modded prices, this map's own config. The **files** are read, never asked for. Their **location** is asked for, and not searched for.

That split is the whole of it. `read_store_prices.py`, `read_game_defs.py` and `read_equipment_market.py` open those files themselves and answer from them, which is why a price is a read and not a question — see the readable list above. But nothing on disk says *where* the install is. It sits outside the savegame, the save does not record it, and an install can live anywhere: off the default path entirely, with a package manifest that is empty or missing. Searching for it is unbounded, and it can fail on a machine where the data is present and perfectly readable.

So the two directories are asked for once, at binding, and recorded. `onboarding-steps/o1-bind-save.md` is where that happens, and it already asks for exactly these two. Do not go looking first: the asking is the method here, not the fallback after a search comes up empty.

**"I have no mods" is a complete answer**, and so is an empty mods folder. A modless farm is an ordinary farm — the modded-price lookups have nothing to add, and every base-game read is unaffected. Record it and move on; do not re-ask, and do not start searching because an answer was empty.

## Three numbers to refuse to invent

All three are genuinely underivable, and all are the kind a session will feel pressure to estimate:

- **A weed yield-loss figure.** `weedState` is the number the game's weed tables are written in
  (`references/game-guide/fields.md` has the per-tool table). The base `maps_weed.xml` gives a
  `factor` per state, but the harvest multiplier that uses it is native code, so no percentage
  can be derived. Report the level, which tool clears it, the herbicide price, and whether the
  farm even owns a sprayer — then let the player judge.
- **A rate, or "days of cover", built from two saves (FM-1001 item 7).** Two readings of the same
  storage a while apart give a *change*, not a rate: nothing in them says whether the change was
  steady, or whether a delivery, refill, sale or harvest happened in between. In one test a
  24-game-minute comparison produced "cover" of 0.3 to 4.9 days per line with no warning, and
  looked like a fact. The rule:
  1. **If the game defines the rate, use that and not two saves.** A production line's input rate
     comes from its recipe (`derived.production_input_demand`, `hours_to_empty`); a fuel or wear
     tier from the vehicle's own figures. Two saves are for rates the game does not publish, such
     as a husbandry's feed use (D-07 says "accumulate N snapshots").
  2. **Every figure built from two saves carries its window next to it**, in the same sentence:
     how long the window was **in game time** (the two saves' `currentMonotonicDay` and `dayTime`
     from `environment.xml`, never wall-clock time — the game clock runs at the player's
     timescale), and this statement: *"a delivery or refill inside this window would change it."*
     Example: "about 3 days of cover at this pace — measured over 24 game minutes; a delivery or
     refill inside that window would change it."
  3. **No figure at all** when: either save's stamp is missing or unreadable, or the two stamps do
     not run forward; the level did not move (that is "no change seen", never infinite cover);
     the level *rose* in the window (something was added, so this window shows no consumption);
     or the two readings straddle a gap in the history (`delta_log.py`: a rate across a gap is a
     fabrication), or the player may have slept in the window (sleep jumps `dayTime` — see
     `time-mechanics.md`; ask, never infer). Say which of these it was.
  4. A figure that passes 1 to 3 is **indicative, not a measurement** — say so, and name the
     longer window (a full day or more of play with no refill) that would firm it up. Do not
     rank lines or recommend an order of action on indicative figures alone.
- **A farm-wide seed bill.** The per-crop rate *is* readable, so quote **cost per hectare**.
  Multiplying it out needs a cropping plan — which crop on which field. That plan now exists as
  `state/field-plan.md` (duty D-02), so a bill for the **planned** fields can be worked out: multiply
  each planned field's hectares by its crop's per-hectare rate, say it covers only the fields that
  have a row, and say how many rows are still `reviewed: no` (an unreviewed row is the manager's
  proposal, not the player's decision). A field with no row has no bill — name it as a gap; never
  assume a crop for it.
