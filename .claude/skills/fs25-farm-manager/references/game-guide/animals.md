# Animal Husbandry

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **primary**, pp.14-15
("Animal Husbandry"). Cross-checked against `FS25-manual_EN.pdf` (base edition, 24pp), same
pp.14-15: **p.15 programmatically confirmed byte-identical; p.14 has one genuine HF-vs-base
difference** (see Cows & Highland Cattle, below). Academy per-animal content previously in this
file has been **re-verified against both PDFs** per the corrected sourcing policy (the FS25
Academy website carries unrevised Farming Simulator 22 content and is no longer a primary
source). None of the detailed Academy productivity percentages, breed names, or breeding-age
figures below were found in either PDF (confirmed by direct text search, not assumed) — they are
kept only as clearly labeled "Academy-sourced, unverified" notes, not as manual fact.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## General mechanics (FS25HF p.14, base p.14 agrees)

- **Purchase & Transport:** buy from the local animal dealer; have animals delivered to your
  pens/barns for a fee, or transport them yourself with a livestock trailer (buy or rent).
- **Housing:** feed, water, and (for some) straw must be supplied. Some housing options have
  automatic water supply or feeding robots. Each housing type has unloading areas for
  depositing food/water.
- **Feed:** each animal has feed preferences; you can grow/mix/distribute feed yourself or buy
  it. Some animals eat Total Mixed Ration (TMR) — see below. Stock up before Winter.
- **Reproduction:** well-nourished, old-enough animals reproduce if there's pen/barn space —
  monitor population.
- **Products:** wool, milk, eggs, manure, slurry (for fertilizing fields), and the animals
  themselves are all sellable.

## Per-animal food & product reference (FS25HF pp.14-15)

| Animal | Food | Product |
|---|---|---|
| Chicken | Wheat, Barley, Sorghum | Eggs |
| Horses | Hay, Oat, Sorghum | Trained Horses |
| Sheep | Grass, Hay | Wool |
| **Cows & Highland Cattle** | Grass, Hay, Silage, Total Mixed Ration (TMR) | Milk, Slurry, Manure |
| Water Buffalos | Grass, Hay, Silage, Total Mixed Ration (TMR) | Buffalo Milk, Slurry, Manure |
| Goats | Grass, Hay | Goat Milk |
| Pigs | Corn, Wheat, Barley, Soybeans, Canola, Sunflowers, Potatoes, Sugar Beets | Slurry, Manure |
| Bees | – (none listed) | Honey |

**Highland Cattle resolved:** the base manual's "Cows" entry is titled **"Cows & Highland
Cattle"** in FS25HF — same food/product list, same section, just a broadened animal name. This
retires the earlier open flag (a previous Academy-only sighting of "Highland Cattle" as a
possible distinct animal type, marked pending). Confirmed by direct diff: it's a naming/breed
addition to the existing Cows entry, not a separate animal — matching the pattern of every other
breed-variant list in this file (e.g. Sheep's later-noted breeds).

Manual per-animal notes:
- **Chicken:** eggs appear as pallets next to the coop; collect with a forklift. Described as
  easy to care for — a good first animal.
- **Horses:** trained by riding (increases value); each horse has an individual fitness level;
  need straw bedding + water.
- **Sheep:** wool pallet must be grabbed at the pasture (pallet fork) and taken to the spinnery,
  or your own production point.
- **Cows & Highland Cattle:** "always produce milk," improved by feeding TMR instead of just
  grass/hay/silage; sellable for profit; milk usable for cheese and other products (FS25HF's
  wording: "cattle"/"animals," slightly more breed-neutral than the base manual's "cows" wording
  — same substance).
- **Water Buffalos:** milk is valuable when processed (e.g. buffalo mozzarella).
- **Goats:** described as easy to handle, low attention, profitable milk (processed into goat
  cheese).
- **Pigs:** need a feed mix of a corn-or-sorghum base + protein (soybeans/canola/sunflowers) +
  root crops, per the manual's Feed Types text — though the per-animal table above lists Sugar
  Beets, not sorghum, as a Pigs food item; **sorghum for pigs is only mentioned in the
  descriptive paragraph, not the icon table**, in both PDF editions identically. Not resolved;
  on the punch list.
- **Bees:** no feed required ("Food: –"); placing hives next to canola/sunflowers/potatoes
  fields also increases those crops' yield — **neither PDF edition quantifies this numerically**
  (confirmed: searched both for the previously-cited Academy figures, not present).

## Feed Types & Components (FS25HF p.15, base p.15 agrees, confirmed byte-identical)

- **Grass and Hay:** most animals need grass; mow it (in a field or wild meadow). For hay, tedder
  the cut grass to dry it; windrower for swaths; loader wagon or baler to collect.
- **Straw:** obtained after harvesting wheat, barley, or oat; collect the swath with a baler or
  loading wagon.
- **Bales:** auto-loaded with a bale collector, or manually with a front-loader + bale fork
  (cheaper, more work).
- **Chaff:** the chopped product of a forage harvester, made from corn, wheat, barley, oats,
  canola, sorghum, soybeans, or sunflowers. Forage harvesters have no tank — need an
  accompanying tractor + trailer.
- **Water:** transported by water trailer; sourced from a lake or a build-mode water tank.
- **Silage:** feed for cows, made from chaff or grass, via two methods — (1) dump into a bunker
  silo and drive over it to compress, then cover and wait for fermentation, or (2) bale grass and
  use a bale wrapper to start fermentation.
- **Total Mixed Ration (TMR):** ingredients are hay, silage, straw, and mineral feed, all
  buyable at the dealership (pallets/bales). Needs a tractor + front-loader + forage mixer wagon
  + bale spike, unless the barn has a feeding robot (auto-mixes from delivered raw ingredients).

## Academy-sourced, NOT in either FS25 manual — unverified

Everything in this section was previously presented as fact, sourced to the FS25 Academy
per-animal tutorials. **None of it was found in either PDF** (confirmed by direct text search for
the specific numbers — productivity percentages, breed names, breeding-age thresholds — not
assumed absent). Kept here as potentially-useful, explicitly-unverified notes rather than
deleted outright, since some of it may still be accurate; verify in-game before relying on any of
it for a management decision.

- **Cows & Highland Cattle** (previously news_id=336): TMR feed = 100% productivity, hay-only =
  80%, grass-only = 40%; dairy breeds (Brown-Swiss, Holstein) vs. non-dairy (Angus, Limousin);
  pasture needs feed+water delivered vs. barn needs feed only; breeding at 18 months+; an example
  TMR mix ratio (4,000 l hay + 4,000 l silage + 450 l mineral feed + fill with straw) explicitly
  tied to one specific piece of equipment, not a universal ratio.
- **Goats** (previously news_id=585): grass-or-hay both reach 100% productivity (no partial-feed
  tier); purchase ages newborn/3mo/16mo; breeding at 8 months+.
- **Chickens** (previously news_id=338): a rooster is required to breed; pasture caps at 30
  chickens; **chickens reportedly need no water at all**; breeding at 6 months+; cannot be
  transported by animal trailer (buy/sell at the barn or livestock trader only).
- **Sheep** (previously news_id=337): 4 cosmetic breeds; grass-or-hay both reach 100%
  productivity; breeding at 8 months+.
- **Pigs** (previously news_id=340): 3 cosmetic breeds; only the pasture (not the pigsty) needs
  water delivered; an optimal feed ratio (50% maize/sorghum + 25% wheat/barley + 20% soy/canola/
  sunflower + 5% potato/sugar beet); breeding at 6 months+.
- **Horses** (previously news_id=339): 8 cosmetic breeds; feed productivity tiers — base
  ingredient + hay = 100%, base alone = 60%, hay alone = 40%; sale value increases only through
  regular riding, not feeding; breeding at 22 months+ (notably older than every other animal
  here).
- **Bees** (previously news_id=341): no purchase/feed/water needed at all; yield-boost figures —
  sunflowers +5%, potatoes +2.5%, canola +2.5%; only one pallet station per farm collects all
  hives' honey.
- **Silage/TMR production** (previously news_id=383, 384): selling silage instead of raw harvest
  reportedly quadruples sale value for grass and corn; bunker-silo compression must reach 100%
  "compaction" before covering.

## Coverage

| Animal | Manual coverage | Academy detail |
|---|---|---|
| Cows & Highland Cattle | ✅ FS25HF p.14 | Unverified notes above |
| Goats, Chickens, Sheep, Pigs, Horses, Bees | ✅ FS25HF p.15 | Unverified notes above |
| Water Buffalos | ✅ FS25HF p.15 | No Academy sub-article was ever identified for this animal specifically |
| Fishing/Aquaculture (Salmon & Trout) | Covered separately — see `fishing.md`, being rebuilt from FS25HF pp.21, 24-26 | — |

No lingering "pending" rows — Highland Cattle is resolved (folded into Cows, above), and every
manual-listed animal has full PDF coverage. The only open items are the punch-list entries
(Pigs' sorghum table/paragraph mismatch, and every Academy figure in the unverified section
above pending an in-game check).
