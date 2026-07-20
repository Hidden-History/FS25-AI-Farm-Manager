# Getting Started, Controls & HUD

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **primary**, pp.3-7
("Controls," "Getting Started," "HUD - Heads Up Display," "Starting out"). Cross-checked against
`FS25-manual_EN.pdf` (base edition, 24pp), same pp.3-7: **p.3 and p.5 confirmed byte-identical;
p.4's Maps section gains a 4th map (Kinlaig) in FS25HF, see below; pp.6-7 differ only in
page-number formatting.** Verification: text extracted with PyMuPDF; the HUD page (p.5) has a
numbered diagram (1-13) whose text was extracted as a flat list matching the manual's own
numbering. Academy "Game Basics" content (previously listed as pending) remains intentionally
out of scope per the "coverage complete, depth weighted by management value" principle — see
`index.md` — this file has no Academy-sourced content to re-verify.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## Controls (FS25HF p.3, base p.3 agrees)

Full rebinding is available in the options menu; the manual lists default bindings for Mouse &
Keyboard and Xbox controller, grouped into: Menu Controls, General Controls, Vehicle Controls,
and Build Mode Controls. Selected defaults worth surfacing (not the full binding list — see the
manual/in-game options menu for the complete table):

| Action | Key (M&KB default) |
|---|---|
| Move | W A S D |
| Shop Menu | P |
| Game Menu | Esc |
| Use Object | R |
| Change Timescale | 7 / 8 |
| Toggle Map View | 9 |
| Enter/Exit Vehicle | E |
| Switch Camera | C |
| Attach/Detach Tool | Q |
| Switch to next Vehicle | Tab |
| AI Worker | H |
| Lift/Lower Tool | V |
| Activate Cruise Control | 3 |
| Refuel or Refill Tool | R |
| Build Mode Menu | Shift + P |

**In-game help:** pressing **F1** opens a Help Window showing your currently available controls
— useful to point a player to instead of memorizing the full binding table.

## Getting Started — Mode Options (FS25HF p.4, base p.4 agrees)

Three starting-difficulty presets, differing mainly in starting finances (and some gameplay
elements), each further customizable:

| Mode | Starting position |
|---|---|
| **New Farmer** | Good machine selection, some land already owned, money "shouldn't be your main concern." Manual's recommendation: "for absolute beginners." |
| **Farm Manager** | Starts with a good amount of money to customize fleet/farmland, but must actively buy in — and "be aware of the loan you have to pay back." |
| **Start from Scratch** | Little to no money; may need contractor work before affording your own land/machines. |

## Maps (FS25HF p.4 — 4 maps; base p.4 has only the first 3)

FS25HF ships **four** maps — the base edition ships three. This is the authoritative list:

| Map | Region/style | Notable detail |
|---|---|---|
| Riverbend Springs | North America | Winding river, creeks/streams, historic buildings |
| Hutan Pantai | East Asia | Lush landscape, mountains, neon-lit port city — "not only for rice paddies" |
| Zielonka | Central Europe | Ponds, a remote/quaint village, "picturesque & fertile" |
| **Kinlaig** (HF-only) | Highlands (Scotland-inspired) | "Rolling hills and open waters" — see `fishing.md` for the full location writeup (castle, harbourmaster, collectibles) |

Each map has a hidden-collectible sub-mechanic: historic machine parts on Riverbend Springs,
"mysterious Crop Orbs" on Hutan Pantai, Golden Apples on Zielonka, and **"multiple pages of a
Captain's Log"** across Kinlaig (p.4's wording) — matching `fishing.md`'s p.26-sourced
"messages in bottles... collected into a notebook" description of the same Kinlaig collectible,
just phrased differently across the two manual sections. Each has a town location to collect
them, which may first require renovating that location (see `production.md`'s Construction
Projects: the Grain Elevator Museum on Riverbend Springs and the Temple Museum on Hutan Pantai;
`fishing.md`'s rebuildable castle on Kinlaig is the same pattern. The manual does not name an
equivalent project for Zielonka's Golden Apples).

## HUD - Heads Up Display (FS25HF p.5, base p.5 agrees)

13 numbered HUD elements, per the manual's own diagram:

| # | Element | What it shows |
|---|---|---|
| 1 | Control Group display | Status of current tools/vehicles (lowered/raised, active/inactive, selected) |
| 2 | Help Window | Currently possible actions for the selected machine |
| 3 | Weather, Time & Money | Current/upcoming weather, time, timescale, account balance |
| 4 | Notifications | AI worker status, expenses, income |
| 5 | Mini-Map | Local area + field information |
| 6 | Attachable Objects | Appears only near an attachable object |
| 7 | Fill Level | How much of a fill type is currently loaded |
| 8 | Speedometer | Current speed, cruise-control speed, vehicle working hours |
| 9 | Fuel and Condition | Fuel level + machine condition |
| 10 | Gears | Selected gear/gear group (automatic or manual transmission) |
| 11 | Steering Assist | Whether GPS-assisted steering is active |
| 12 | Crosshair (on foot only) | Screen center — used to grab objects / inspect fields, machines, etc. |
| 13 | Chat Window (multiplayer only) | Multiplayer chat |

## Starting Out (FS25HF p.6, base p.6 agrees)

Three main pursuable activities (the manual notes there's more beyond these — production chains
and construction projects "allow you to grow further," see `production.md`):

- **Arable Farming** — "the heart of Farming Simulator."
- **Animal Husbandry** — tending animals; the manual notes you can grow the animals' own feed
  crops yourself "maximizing efficiency of the whole operation."
- **Forestry** — described as lucrative but requiring machine skill and budget (see
  `forestry.md`).

**Purchasing Land:** starting land ownership depends on the chosen mode (above); more land is
buyable/sellable via the menu. You cannot work or build on land you don't own, **except via
contract work** (see `finances.md`'s Contracts section).

**Create & Extend Fields:** a plow can create new fields on owned land, or expand/combine
existing ones (cross-reference: `fields.md`'s Plowing section already covers the "create fields"
plow function in mechanical detail — this page is the strategic framing: "buy smaller fields
close together and combine them" as an early-game money-saving tip).

## First Machines (FS25HF p.7, base p.7 agrees)

The manual's recommended starter equipment set for an arable-farming start (leasing is suggested
as an alternative to buying, "especially the expensive ones"):

| Machine | Why |
|---|---|
| Tractor | Needed to power most other tools — check its power rating against each tool's requirement |
| Cultivator (+ a plow for periodic plowing) | Prepares the field by loosening soil |
| Seeder or planter | Sows/plants — pick the machine matching your target crop |
| Weeder | Removes weeds to avoid a yield penalty |
| Fertilizer spreader | Fertilizes and (if the specific spreader supports it — check the dealership icon) limes the soil |
| Combine harvester + header | A grain header is recommended first since it can harvest many crops |
| Trailer | Transports crops to selling points/factories |

This list is the "why you need it" framing; the mechanics of each tool (liming, weeding stages,
fertilizer types, etc.) are covered in full in `fields.md` — not duplicated here.

## Not covered on these pages

No numeric starting-balance figures for any of the three modes, no full control-binding table
(only a curated subset above — see the manual/in-game menu for the complete list), and no wage
or price data for the First Machines list. None of these are asserted here.
