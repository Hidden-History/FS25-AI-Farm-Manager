# Productions & Constructions

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **primary**, pp.18-21
("Productions & Constructions"). Cross-checked against `FS25-manual_EN.pdf` (base edition, 24pp),
pp.18-21: **p.18 (Production Chains) and p.19 (first 12 factories) confirmed byte-identical.**
**p.20 is base's page plus 4 new factories appended** (Stone Mason, Preserved Food Factory,
Quarry, Fish Food Factory) — additive only, nothing removed or changed. **p.21 is base's
Construction Projects/Build Mode Menu content with a new fish-farming production overview
(Young Fish Breeding, Offshore Aquaculture) prepended** — covered in `fishing.md`, not
duplicated here. Verification: all dense Production Overview entries **visually cross-checked**
against rendered page images — each factory prints inputs (download-icon list) then outputs
(upload-icon list); confirmed against the icons in the image, not inferred from text order alone,
including for all 4 new HF-only factories. No Academy sub-article covers this topic.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## Production Chains (p.18)

- Instead of selling harvest directly, you can process it further to raise the end product's
  selling price — via local factories, or your own (build-mode) factory if you have the budget.
- **Factories** process harvest into goods/resources. Manual's own example: a sawmill makes
  wooden planks from logs; the planks can then go to a carpentry shop to become furniture — "you
  earn way more money compared to just selling logs" (i.e. multi-stage chains compound value).
- **Farm Shops & Selling Stations**: other businesses buy your crops/products directly; some
  (e.g. the bakery) also produce goods. Farm shops specifically request certain goods for
  delivery, providing steady income.

## Production Overview — all factories/production points (pp.19-20)

Each row's **Inputs** are what you deliver; **Outputs** are what the point produces for sale
(both taken directly from the manual's per-building icon lists). A `*` on the building name
means the manual notes "Different Versions available!" for it — treated as a manual fact, not
elaborated further since the manual doesn't specify what the versions differ in.

| Production point | Inputs | Outputs |
|---|---|---|
| Grain Mill * | Wheat, Barley, Oat, Sorghum, Long Grain Rice, Rice | Flour, Rice Flour |
| Dairy * | Milk, Goat Milk, Buffalo Milk, Sugar | Cow Milk (bottled), Buffalo Milk (bottled), Goat Milk (bottled), Buffalo Mozzarella, Cheese, Goat Cheese, Chocolate, Butter |
| Sugar Mill * | Sugar Beet, Sugar Beet Cut, Sugarcane | Sugar |
| Oil Mill * | Canola, Sunflowers, Olives | Canola Oil, Sunflower Oil, Olive Oil |
| Sawmill * | Fir Tree | Planks, Planks Long, Wood Beams, Prefab Wall, Wood Chips |
| Paper Factory * | Fir Tree | Paper Roll, Carton Roll |
| Spinnery * | Wool, Cotton | Fabric |
| Soup Factory * | Potatoes, Carrots, Parsnips, Red Beet, Rice, Long Grain Rice | Potato Soup, Carrot Soup, Parsnip Soup, Red Beet Soup, Soup Cans, Noodle Soup |
| Cement Factory * | Stones | Cement Bags, Cement Bricks, Roof Plate |
| Cooper * | Planks, Planks Long | Barrel, Bathtub, Bucket, Wood Chips |
| Canning Factory * | Carrots, Red Beet, Parsnips, Peas, Cabbage, Spinach, Rice, Long Grain Rice | Pr. Food Carrots, Pr. Food Red Beet, Pr. Food Parsnips, Canned Peas, Fermented Cabbage, Spinach Bag, Rice Bags, Rice Boxes |
| Carpentry * | Fir Tree, Planks, Planks Long | Furniture |
| Tailor Shop * | Fabric | Clothes |
| Potato Processing Plant * | Potatoes, Rice, Long Grain Rice, Canola Oil, Sunflower Oil, Olive Oil | Potato Chips, Rice Rolls |
| Rope Maker * | Wool, Cotton | Rope |
| Grape Processing Unit * | Grapes | Grape Juice, Raisins |
| Bakery * | Flour, Sugar, Milk, Eggs, Butter, Strawberries | Bread, Cake |
| Biogas Plant 1MW * | Slurry, Manure, Silage, Sugar Beet Cut | Digestate |
| Greenhouse * | Water | Strawberries, Lettuce, Tomatoes, Spring Onions, Cabbage, Chili Peppers, Garlic |
| Mushroom Greenhouse * | Water | Oyster Mushroom, Enoki |
| Greenhouse for Rice Saplings * | Water | Rice Saplings |
| **Stone Mason** (HF-only) | Big Stones | Castle Stones, Roof Shingles |
| **Preserved Food Factory** (HF-only) | Canola Oil, Sunflower Oil, Olive Oil, Rice Oil, Onions, Potatoes, Red Beet, Carrots, Parsnips | Soup Cans, Red Beet Soup, Potato Soup, Carrot Soup, Parsnip Soup, Onion Soup, Onion Salt, Fried Onion |
| **Quarry** (HF-only) | Water | Castle Stones |
| **Fish Food Factory** (HF-only) | Canola Oil, Sunflower Oil, Olive Oil, Rice Oil, Flour, Soy Beans | Fish Food |
| **AS 25** (HF-only, onion topper/packer) | Onions | Onions (Packed) |

**Two gaps this resolves from earlier passes:**
- **Onion-processing outputs** (fried onions, onion salt, onion soup) — previously known only
  from the now-deprioritized Academy Onions article, now **officially confirmed** via the
  Preserved Food Factory entry above, PDF-sourced.
- **Fish Food production chain** — previously known only from Academy content in `fishing.md`,
  now **officially confirmed** via the Fish Food Factory entry above: inputs are 4 oils + flour +
  soy beans, output is Fish Food (feeds `fishing.md`'s Young Fish Breeding / Offshore Aquaculture,
  both of which also take Fish Food as their sole input per FS25HF p.21 — see `fishing.md`).
- **"AS 25"** is visually confirmed as its own small production point (separate building box, not
  part of Fish Food Factory as flat-text extraction initially suggested) — matches the "Holaras
  AS 25" onion topper machine name from the now-deprioritized Academy Onions article, an
  incidental cross-confirmation of a detail from a source that's otherwise no longer primary.

Notes, faithful to the source:
- The three greenhouse entries above are **production points that consume only Water** to
  produce their crop — distinct from the field-planted greenhouse crops list in `crops.md`
  (Manual p.13), which names the same crop set without a production-chain framing. Both are
  manual-sourced; not a conflict, two different manual sections describing the same crops from
  different angles.
- The Biogas Plant is the only production point whose single output (Digestate) is itself
  explicitly cross-referenced elsewhere: `fields.md`'s Fertilizing section notes digestate is
  "a free byproduct you gain from selling manure or silage at the biogas plant," applied like
  slurry.
- Sugar Mill's "Sugar Beet Cut" input (distinct from plain "Sugar Beet") and the Biogas Plant's
  matching "Sugar Beet Cut" input are both taken verbatim from the manual; **no page explains
  what distinguishes "Sugar Beet" from "Sugar Beet Cut"** as a deliverable good — not asserted
  here.

## Construction Projects (FS25HF p.21, base p.21 agrees — HF prepends fish-farming content, see `fishing.md`)

Larger, town-shaping projects requiring "attention and commitment," rewarded on completion:

- **Grain Elevator Museum** (Riverbend Springs map): restore a historic grain elevator into a
  museum; gather/deliver resources to display artifacts hidden around the city.
- **Temple Museum** (Hutan Pantai map): rebuild temple grounds to display "Crop Orbs" hidden
  around the map.
- **Repeatable Constructions**: smaller ongoing businesses (the manual names a wagon maker, a
  playground-tractor builder, a piano maker, "and other businesses") requiring continual resource
  deliveries, each completed delivery rewarded.

**Not covered on this page:** the manual names the two large construction projects by map
(Riverbend Springs, Hutan Pantai) but doesn't mention an equivalent large project for the third
map (Zielonka) — not asserted here as either present or absent.

## Build Mode Menu (FS25HF p.21, base p.21 agrees)

Category breakdown as given by the manual:

| Category | Contents |
|---|---|
| Buildings | Sheds, silos, silo extensions, containers, tools |
| Production | Factories, selling points, greenhouses, orchards, generators |
| Animals | Pens (varied shapes/sizes/functionality) |
| Decorations | Fences, street lights, and other detail items |
| Landscaping | Sculpting, painting, tree/plant placement tools |
