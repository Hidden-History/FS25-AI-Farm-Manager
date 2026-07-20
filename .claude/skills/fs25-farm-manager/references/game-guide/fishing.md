# Fishing & Aquaculture

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **the only source**;
pp.21 (fish-farming production overview, within "Productions & Constructions"), pp.24-26
("Highlands Fishing": Aquafarming, Catching Fish, Kinlaig). **Not covered by the base
`FS25-manual_EN.pdf` (24pp) at all** — Highlands Fishing is confirmed HF-edition-exclusive
content, introduced by name: "Aquaculture is a new form of farming, introduced with the
Highlands Fishing expansion" (p.24). This supersedes the previous Academy-sourced version of
this file entirely — every fact below is manual-PDF-sourced, not Academy-sourced. Verification:
text extracted with PyMuPDF; p.21's production data **visually cross-checked** against the
rendered page image for input/output accuracy.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## Fish Food (p.24)

- Needed to raise fish. Buy it at the shop (Animals → Food) or the warehouse, or produce it
  yourself at the **Fish Food Factory** (inputs: canola/sunflower/olive/rice oil + flour + soy
  beans — see `production.md`) — self-producing "may be more cost-effective if your overall
  operation allows it."

## Fish Breeding (p.21, p.24)

- Build the **Fish Breeding Facility** via Construction → Production Chain → Aquaculture
  (manual p.21 calls the same building "Young Fish Breeding" in its production-overview table —
  same facility, two names used across the manual).
- Deliver fish food to the facility; more fish food increases production. It produces **juvenile
  salmon and trout** ("appearing in boxes"/crates).
- Per the p.21 production table: **input is Fish Food only; output is Young Trout and Young
  Salmon** — both species come from the same single building, not species-separated facilities.

## Transporting & Selling Fish (p.24)

- Use a forklift to sell crates of juvenile fish directly at the **fish market**, or use a crane
  to load them onto a **cargo ship** for delivery to an **offshore aquafarm** to raise them into
  adult fish for higher profit.
- **Offshore Aquaculture** (p.21 production table): input is Fish Food + Young Trout + Young
  Salmon; output is Trout and Salmon (adult). Deliver crates of juvenile fish to the aquafarm,
  place them on the green platform; adult fish spawn on the next platform, collected/sold via
  crane.
- **Automatic selling**: open "Production Chains," select "Offshore Aquaculture," set the fish
  output to "Sell."

**Note on a previously-held claim, now dropped:** an earlier (Academy-sourced) pass of this file
stated Trout could be raised in a separate "fish lake" OR offshore, while Salmon was
offshore-only. **The manual's own building list has no separate "fish lake"** — only Young Fish
Breeding and Offshore Aquaculture, both handling trout and salmon identically. That species-
housing distinction is not corroborated here and is likely inaccurate; dropped rather than
carried forward unverified.

## Catching Fish (p.25)

- Buy a fishing rod at the dealer (Hand Tools category).
- **Places to fish:** near any river/ocean, or from a sports boat out at sea.
- **Mechanic:** hold the action button to cast (longer hold = farther cast) → wait for a bite
  indicator → press the action button at the right moment or the fish escapes → reeling minigame
  (hold to raise the bait, release to lower it, follow the fish's position until it tires).
- Framed as a skill that improves with practice ("keep at it to improve your fishing skills and
  maybe get rewarded").

## Fishing Boats (p.25)

Both boat types are sold **only at the Boat Store at the harbor** (next to the fish market), not
the regular vehicle dealership.

| Boat | Purpose |
|---|---|
| Cargo Vessel | Transports goods to offshore aquafarms; mounted crane for lifting fish/feed pallets; has a ramp so a forklift can drive aboard for loading |
| Sport Boat | Smaller, not for cargo; lets you fish manually out at sea |

## Kinlaig — the Highlands Fishing map (p.26)

A fourth FS25 map (alongside the base game's Riverbend Springs, Hutan Pantai, Zielonka),
Scottish-Highlands themed:

- Old town with a castle and a bay lighthouse at the landing point.
- **Rebuildable castle** on a hill — a construction project requiring delivered resources (same
  pattern as the base manual's Grain Elevator Museum/Temple Museum, see `production.md`).
- Other points of interest: a historic bridge with a passing train, "mysterious rock circles,"
  and more, framed as exploration content.
- **Harbourmaster** (named: Alasdair) — an NPC who explains fishing mechanics.
- **Collectibles:** messages in bottles washed up on shore, collected into a notebook, telling a
  story across all the pages.

## Onions — confirmed official crop, growing procedure (p.26)

The manual explicitly introduces Onions as new HF content: *"With onions, a new crop is
introduced as well!"* This resolves the earlier open question about Onions' manual status —
it's officially part of Highlands Fishing (see `crops.md`'s data table, which already carries
its yield/price/seed/timing data from p.10).

- Root crop needing specialized sowing/harvesting equipment (same family as Potatoes/Sugar Beet/
  Carrots/Parsnips/Red Beet in `crops.md`).
- Sown March or April, harvested August or September (matches the data table exactly).
- **Ready-to-harvest signal:** green tops have dried.
- **Harvest is a 2-machine, multi-step process**, per the manual's own description: (1) cut the
  haulms and pull onions from the soil — front attachment does the pulling, a rear attachment
  cleans them and drops them into rows; (2) the rows are collected and further cleaned by a
  separate onion harvester with the correct header.
- Sell raw, or pack into "Onions (Packed)" (see `production.md`'s "AS 25" entry).

## Coverage

Everything on FS25HF pp.21, 24-26 relevant to fishing/aquaculture management is covered above.
No Academy content remains in this file — the previous per-animal-style Academy detail (species-
specific housing restrictions, cargo-vessel loading mechanics) has been dropped where
uncorroborated (the fish-lake/species-housing claim) or superseded by the manual's own account
(everything else).
