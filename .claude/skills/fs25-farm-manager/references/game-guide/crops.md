# Crops & Arable Farming

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **primary**, pp.9-10
("Arable Farming — Field Crops," the 26-crop data table) and p.13 (Storing/Greenhouse/Seasonal),
p.26 (Onions' growing account). Cross-checked against `FS25-manual_EN.pdf` (base edition, 24pp),
same pages. Where they differ, FS25HF wins as the fuller/newer superset — differences are called
out explicitly below, not silently resolved. Verification: both PDFs' crop-data tables extracted
with PyMuPDF, then **visually cross-checked against rendered page images** for both editions.
Academy content previously in this file has been **re-verified against both PDFs** per the
corrected sourcing policy (the FS25 Academy website carries unrevised Farming Simulator 22
content and is no longer a primary source).

For field-preparation mechanics (liming, plowing, fertilizing, weeds, rolling, mulching,
sowing/planting, stones) see `fields.md`, also rebuilt from these PDFs — not duplicated here.

**This file is a distillation, not the live source of truth** — the in-game Help menu is
authoritative and can't go stale the way a copy can; see the in-game Help for the live version of
this content.

## All 26 field crops (FS25HF pp.9-10, cross-checked vs. base pp.9-10)

FS25HF states "In Farming Simulator 25 Highlands Fishing there are 26 different main crops you
can grow on fields" — one more than the base edition's 25. **Onions is the addition**, confirmed
with full data on FS25HF p.10; it was previously flagged in this file as "not one of the manual's
25 crops" based on an Academy-only sighting — that flag is now resolved: Onions is genuine FS25
content, just HF-edition-exclusive relative to the base manual. Table below is alphabetical.

| Crop | Yield/ha | Avg. selling price | Seeds/ha | Planted | Harvested |
|---|---|---|---|---|---|
| Barley | 19,200 l | €938 | 265 l | Sep–Oct | Jun–Jul |
| Canola | 11,600 l | €1,808 | 7 l | Aug–Sep | Jul–Aug |
| Carrots | 154,000 l | €395 | 10 l | Apr–Jul | Aug–Nov |
| Corn | 18,400 l | €1,139 | 53 l | Apr–May | Aug–Nov |
| Cotton | 9,940 l | €3,755 | 50 l | Feb–Mar | Oct–Nov |
| Grapes | 18,400 l | €1,808 | – (n/a) | Mar–May | Sep–Oct |
| Grass | 87,400 l | €135 | 160 l | Mar–Nov | Jan–Dec |
| Green Beans | 13,950 l | €2,160 | 280 l | Apr–Jun | Aug–Nov |
| Long Grain Rice | 18,000 l | €1,589 | 500 l | Apr | Sep |
| Oat | 11,400 l | €1,596 | 340 l | Mar–Apr | Jul–Aug |
| **Oilseed Radish** | 9,000 l | **not stated** | 340 l | Mar–Oct | **not stated** |
| **Onions** (HF-only, not in base manual) | 70,000 l | €750 | 5 l | Mar–Apr | Aug–Sep |
| Olives | 18,400 l | €1,808 | – (n/a) | Mar–Jun | Oct |
| Parsnips | 139,000 l | €392 | 10 l | Apr–Jun | Aug–Nov |
| Peas | 9,600 l | €3,119 | 250 l | Mar–Apr | Jul–Sep |
| Poplar | 56,400 l | €119 | 1,500 l | Mar–Aug | Jan–Dec |
| Potatoes | 82,600 l | €666 | 3,733 l | Mar–Apr | Aug–Oct |
| Red Beet | 115,600 l | €366 | 40 l | Apr–Jun | Aug–Nov |
| Rice | 13,200 l | €3,300 | 156 l | Apr–May | Aug–Sep |
| Sorghum | 16,400 l | €1,290 | 35 l | Apr–May | Aug–Sep |
| Soybeans | 9,000 l | €2,333 | 214 l | Apr–May | Oct–Nov |
| Spinach | 46,200 l | €659 | 10 l | Mar–May | Jan–Dec |
| Sugar Beet | 115,600 l | €516 | 34 l | Mar–Apr | Oct–Nov |
| Sugarcane | 226,800 l | €357 | 12,000 l | Mar–Apr | Oct–Nov |
| Sunflowers | 10,400 l | €2,018 | 143 l | Mar–Apr | Oct–Nov |
| Wheat | 17,800 l | €1,011 | 308 l | Sep–Oct | Jul–Aug |

Notes on the table above, faithful to what the sources do and don't say:
- **Genuine FS25HF-vs-base difference, not an extraction gap:** the base manual gives Oilseed
  Radish an Avg. selling price (€1,596) and a Harvested-during window (Jan–Dec). **FS25HF's
  Oilseed Radish entry omits both fields entirely** — visually confirmed on the rendered page,
  not a parsing error; the entry simply has 3 fields (Yield, Seeds, Planted) instead of the usual
  5. Not resolved here: could mean Oilseed Radish is priced/handled differently in HF (e.g.
  purely a catch crop, never sold — consistent with `fields.md`'s existing note that it's mainly
  used to fertilize via cultivating it under), or could be a content gap in the HF manual itself.
  Flagged in the verification punch list rather than guessing; the base manual's values are kept
  in the "faithful transcription" sense but should not be assumed still accurate for HF.
- Onions' Mar–Apr / Aug–Sep window matches what the (now-deprioritized) Academy article stated —
  one of the few Academy facts that cross-validates against an official PDF rather than needing
  the "unverified" treatment.
- Grapes and Olives show "–" for Seeds per ha in both PDFs — planted differently (orchard/
  vineyard placement via build mode), not sown from seed.
- Oat and Oilseed Radish shared an identical Avg. selling price (€1,596) and Seeds/ha (340 l) in
  the base manual; with HF removing Oilseed Radish's price field, this coincidence no longer
  applies in the HF edition specifically.
- **These are "average" selling prices printed in the manual as a single reference point** — both
  PDFs' p.13 state prices fluctuate over time in-game. Not a live/current price.
- Planted/Harvested windows are the **base-game default calendar**. Per `crop-calendar.md`'s
  existing caveat, maps commonly override these — this table is a reference point, not a
  guarantee for any specific save/map.
- **All 24 other crops' data is byte-for-byte identical between FS25HF and the base manual** —
  confirmed by direct text diff of both PDFs' pp.9-10, not just a visual spot-check.

## Storing (FS25HF p.13, base p.13 agrees — confirmed byte-identical)

- Select crops can be stored in a silo to sell later; watch price fluctuations on the prices
  screen (which shows what each business currently pays).
- Silos are placed via build mode.

Neither PDF edition gives a per-crop silo-eligibility breakdown beyond "select crops" — see the
unverified note below for what a prior Academy-sourced pass had claimed per crop.

## Onions — confirmed official crop and growing procedure (FS25HF p.26)

Onions is confirmed official Highlands Fishing content — the manual states outright: *"With
onions, a new crop is introduced as well!"* Full growing detail is in `fishing.md` (the manual
covers Onions within its "Highlands Fishing" section, not the Arable Farming section, since it's
introduced alongside the expansion) — not duplicated here beyond the data-table row above.
Summary: root crop, sown Mar–Apr, harvested Aug–Sep (matches the table), 2-machine harvest
process (cut+pull, then collect+clean), sells raw or as "Onions (Packed)" via the AS 25 packer
(see `production.md`).

## Academy-sourced, NOT in either FS25 manual — unverified

Everything below was previously presented as fact, sourced to Academy per-crop "How to Sow and
Harvest" tutorials and the Crops 101 overview. **Searched both PDFs directly for the specific
figures/terms below — none found** (e.g. "quadruple," "haulm" [only in the now-separate Onions
context], "2,000 l"/"20,000" bale sizes, "60%" rice water level — all absent or coincidental
matches only). Kept as potentially-useful unverified notes, not fact; verify in-game before
relying on any of it.

- **Crop categories** (previously news_id=297): grain crops (wheat/sorghum/barley/oat/canola/
  soybeans, shared harvester+header), root crops (potatoes/sugar beet, no-silo + must-plow-every-
  harvest), orchards (olives/grapes, build-mode placement), "other" (cotton/corn, expensive
  specialized equipment). A reasonable organizing schema, not manual-stated.
- **Per-crop silo eligibility** (previously news_id 302/306/307/305/502/513/514/558/303): Sugar
  Beet/Cotton/Sugarcane/Poplar/Carrots/Parsnips/Red Beet reportedly can't silo-store; Spinach
  reportedly can't be stored at all; Sunflowers reportedly confirmed storable.
- **Perennial/regrowing crops** (previously news_id 307/305/299/300): Sugarcane and Poplar
  reportedly regrow without replanting (Poplar reportedly never withers); Grapes reportedly needs
  annual leaf-cutter pruning; both Sugarcane and Poplar reportedly need tractor weight
  attachments.
- **Root crop shared handling** (previously news_id 301/302/502/513/514): reportedly need a hoe
  not a weeder, an optional ridge-former step, and Sugar Beet reportedly needs a separate
  haulm-topping pass plus a ~185hp harvester.
- **Rice family water management** (previously news_id 556/557): reportedly needs daily water-
  pump checks, a 60%-fill-before-sowing rule for Rice specifically, and Long Grain Rice
  reportedly needs fertilizing only once instead of twice.
- **Grains shared facts** (previously news_id=298): reportedly Canola is the only grain sowable
  at a seasonal-growth save's August start; reportedly wheat/barley/oat produce straw on
  harvest.
- **Corn/Maize dual harvest path** (previously news_id=304): reportedly grain harvest (Oct–Nov)
  vs. chaff harvest (Aug–Sep) are different windows for the same crop depending on purpose —
  plausible given `fields.md`'s chaff-timing note, but not PDF-confirmed for Corn specifically.
- **Cotton mechanics** (previously news_id=306): reportedly direct baling, a 2,000l/20,000l
  bale/module size, spinnery-only selling, and a 7-vs-6-row manual-vs-helper harvest rate.

## Timing cross-check against the manual — Academy claims now discounted, not disproven

A prior pass compared Academy per-crop timing claims against the manual's data table and found 4
apparent discrepancies (Olives, Potatoes, Green Beans, Peas). **Re-examined under the corrected
sourcing policy:** both manual editions agree with each other on every crop's timing (see the
"byte-for-byte identical" note above) — there is no PDF-vs-PDF conflict for any of these 4 crops.
The discrepancies were entirely Academy-vs-manual, and the Academy is no longer treated as
reliable. **Resolution: the manual's timing stands as stated in the data table above; the
Academy's conflicting claims (Olives Aug–Sep, Potatoes harvest-ends-Sep, Green Beans plants-
through-Jul, Peas' ambiguous wording) are discounted, not carried forward as open conflicts.**
Kept as a historical note, not a punch-list item — there's nothing left to verify against a PDF
here since both PDFs already agree.

## Greenhouse Crops

**Source:** FS25HF p.13 (base p.13 agrees, confirmed byte-identical).

Greenhouses are an additional income source, separate from the 25 field crops above. The manual
lists these greenhouse crops by name (no yield/price/seed data given for them, unlike the field
crops table): Strawberries, Chili Peppers, Cabbage, Spring Onions, Garlic, Oyster Mushrooms,
Lettuce, Enoki, Tomatoes, Rice Saplings.

- Sold at various selling points or processed further.
- A supplementary water tank can be placed next to a greenhouse to increase water capacity —
  greenhouse plants require fresh water.

**Not covered on this page:** the manual does not give per-greenhouse-crop yield, price, seed
amount, or planting/harvest windows — unlike the field-crop table above, none of that is stated
here and none is inferred.

## Seasonal Farming, Weather & Weather Events

**Source:** FS25HF p.13 (base p.13 agrees, confirmed byte-identical).

- FS25 has four seasons (spring/summer/fall/winter), each affecting gameplay.
- The seasonal crop calendar governs planting/harvest windows (see table above); prices also
  fluctuate by time of year. "Seasonal growth" can be deactivated to allow planting/harvesting
  any time.
- You cannot harvest during snow or rain — wait for it to stop; watch the weather-forecast icon
  (top right) for upcoming changes.
- Snow makes roads slippery and affects vehicle handling; snow can be toggled off in game
  settings.
- Weather events (twisters, hail) can occur in certain seasons and can damage fields and bales
  left outside storage — inspect fields after a storm for damage.

## Rebuild status

All 26 crops' data is PDF-sourced and cross-checked between both manual editions (see the data
table). Onions has a full official growing account (p.26, see above). All previously Academy-
sourced per-crop management detail has been re-verified against both PDFs and consolidated into
the single "Academy-sourced, unverified" section above (kept, not deleted, per the corrected
sourcing policy) — nothing in this file is presented as fact without a PDF citation. No lingering
"pending" banners remain.
