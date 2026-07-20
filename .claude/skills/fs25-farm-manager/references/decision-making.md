# Decision-Making Policy

This is the part that makes you a manager instead of a report generator.
For each area below, don't just surface data — form a recommendation, say
why, and let the player decide.

**This file is general, portable policy — how to weigh a contract, a
purchase, a sale, in principle.** This farm's own priorities, risk appetite,
and any self-imposed rules (e.g. a notional cash/debt ledger) live in
`sanctum/identity/decision-making.md`, written once at onboarding from
`templates/decision-making.md`. Read both, but keep them straight: if the two
ever seem to disagree, the sanctum copy wins for this farm — it's the
judgment layer only this farm's owner supplied. If this farm tracks an
adjusted cash figure instead of the save's raw `money`/`loan`, use that one
and say which figure you're quoting, every time you mention cash.

### Contracts (from `read_missions.py`)

Every mission in the output has a `status`. Use it to split contracts into
two buckets before saying anything:
- **On offer, not yet accepted** — evaluate whether to recommend taking it
- **Already accepted / in progress** — evaluate whether it's at risk

For each, weigh:
- **Payout efficiency**: reward ÷ expected liters (or ÷ estimated time if it's
  not a liters-based job) — but only once the reward is actually known.
  Field-tied contracts routinely report a reward of `0` while still on offer,
  because the game computes the real payout at accept-time and hasn't written
  it yet — that is **unknown, not zero**. A parser that's been fixed for this
  will hand you `reward: null` plus a note saying so; treat that as your
  signal to say "payout isn't known until accepted — check the in-game
  contract screen if it matters before deciding," not as a reason to divide,
  and never as "pays nothing, skip it." Standalone jobs (tree transport,
  deadwood, rock clearing) typically do carry a real flat fee already — that
  contrast is how you know a `0` on a field-tied job is a placeholder, not a
  verdict.
- **Overlap**: does the contract's field match a field you already plan to
  work this session? Free money if so — say so explicitly. This is only
  valid once field ownership is actually resolved and cached somewhere durable
  (a savegame's field→farmland mapping is not always derivable from the
  fields file alone — see SKILL.md for whether this installation has that
  resolved). If there's no confirmed owned-field list yet, say plainly that
  overlap can't be evaluated rather than guessing at a match — an invented
  "yes, that's one of yours" is worse than no answer.
- **Deadline risk**: compare the mission's end day (its `endDate` child's
  `endDay`) against the current in-game day (`read_environment.py`'s
  `current_day`, sourced from `<currentDay>` — there is no `daysSinceStart`
  field anywhere in this toolkit's output; don't join against a name that
  doesn't exist). Before flagging urgency, ask whether this looks like a real
  deadline or routine mission-pool churn: many field-tied contract types
  reappear/refresh daily with an end day of "today" as a matter of course —
  that's rotation, not risk, and flagging it as urgent every session
  manufactures false pressure out of normal noise. A contract type carrying a
  genuine multi-day window losing time is worth a real flag. When the honest
  read is "not much here is urgent, but not much is workable either," say
  that — e.g. "of what's on offer, only N were runnable with the fleet you
  have; tomorrow's batch may not repeat that" is a more useful sentence than
  a deadline countdown on contracts that rotate daily regardless.
- **Equipment fit**: does the player own (or is renting) equipment that can
  do this job? Don't recommend a job they can't currently execute.

Recommend, don't auto-decide: "This wheat contract at Field 1 is good money
and you're already there — worth taking?" not silently assuming yes.

### Storage & selling (from `read_placeables.py`)

- Track silo/storage fill levels against capacity. If something's near full,
  flag it — risk of losing yield to overflow, or a sign it's time to sell.
- If a fill type is high and there's a matching sell contract or a normally
  good sell price, connect the two: "You've got a full silo of wheat and
  that harvest contract wants exactly that — worth delivering now?"
- Contract grain and your own grain are not the same asset: grain worked
  under a contract typically belongs to the contractor, but grain from your
  own fields is yours to store and time against the price calendar. Don't
  collapse "take the contract" and "harvest your own ripe field" into the
  same recommendation — the second can outrank the first even at a lower
  headline number, because you keep the optionality to sell into a better
  window later.
- If calibration hasn't been done yet for this file, do the lookup silently
  (see Calibration) rather than showing the player raw JSON.

### Animal husbandry (from `read_placeables.py`)

*(If this farm owns no husbandry or production buildings yet, this section
and the next are inert for now — worth a skim, not a full re-derivation,
until the farm actually has one.)*

- Check food/water/straw levels against consumption — flag anything running
  low before it becomes a crisis, not after.
- Track output (milk/manure/wool/eggs) accumulation — remind the player when
  it's worth collecting/selling.
- Maintain `sanctum/state/husbandry-roster.md` and a dossier per building using
  `templates/husbandry-dossier.md`, same pattern as field dossiers.

### Equipment — repair, sell, and buy

**Repair/condition** (from `read_vehicles.py`): flag high wear/damage before
it causes a breakdown mid-job, and low fuel before a session gets derailed.

**Used equipment for sale** (from `read_sales.py`): when listings are found,
evaluate against the farm's actual needs — don't recommend buying just
because something's on sale. Ask: does an active/likely contract need
equipment we don't own? Is something in the current fleet worn out enough
that replacing beats repairing? Cross-check against
`sanctum/state/equipment-shopping-list.md` — if the player previously said "watch
for a used sprayer," flag it the moment one appears.

**New equipment**: store prices for anything not yet owned are static
install/mod data — a plain price tag sitting in the game's own files, not
something to wait on the player to volunteer (see SKILL.md's "Data sources
at a glance" for exactly where to look, e.g. a `paths.store_data` pointer to
the base-game and modded vehicle/placeable XML). Look the price up yourself
before costing out a purchase. Only ask the player if a genuine lookup — the
right file, for the right item — comes up empty; when that happens, log
whatever they report in `sanctum/state/equipment-shopping-list.md` with the date so
the gap doesn't get asked about twice.

**Sell recommendations**: idle equipment (not used across several sessions,
per the roster) or equipment far exceeding what current field count/size
needs is worth flagging as a sell candidate — cash beats a rusting asset.

### Selling — where and when

- `read_prices.py` gives **relative** per-station signals — which station looks
  better right now, and whether a price is sitting in a plateau. It is **not** an
  absolute price source (`mean_value` is `null` on anything never traded). For the
  actual sell price of a fill type, use `read_fill_prices.py`. Use the two together:
- When multiple stations accept the same fill type, compare `mean_value` and
  `is_in_plateau` (from `read_prices.py`) across them — recommend the better one,
  not just the nearest one.
- Don't state prices as exact facts (the underlying curve isn't fully
  solvable) — frame as "X looks like it's in a good pricing window right
  now" rather than quoting a guaranteed number.
- Combine with storage levels: a full silo + a station currently in a good
  plateau is a "sell now" recommendation worth surfacing proactively.

### Production chains (from `read_placeables.py`)

- Track input stock vs. consumption and output accumulation, same pattern as
  storage/husbandry. Flag when a production building is about to stall for
  lack of input, and when output is worth collecting/selling.
- Maintain `sanctum/state/production-roster.md` and a dossier per building using
  `templates/production-dossier.md`.
- Connect to selling logic above when the output is something sellable.

### Field expansion (unowned fields)

- Field ownership, a parcel's **area**, and its **cost** are all readable —
  `read_farmland_areas.py` decodes the map's `infoLayer_farmlands.grle` raster
  for per-parcel hectares, cost, and owner (it self-checks against `farms.xml`'s
  `<fieldPurchase>` every run — see SKILL.md). Read the area and cost straight
  from it rather than treating "the price" as one opaque number to wait on the
  player for, and **never ask how many hectares a parcel is** — ownership and
  area are resolved (SKILL.md). Only fall back to asking if the decoder's gates
  fail on a given map. Log the area and cost you read in
  `sanctum/state/field-price-watchlist.md`.
- Weigh any purchase against current cash/loan position before recommending
  it — don't recommend buying land while cash is tight without saying so, and
  remember the notional-cash note at the top of this file if this farm keeps
  one.
