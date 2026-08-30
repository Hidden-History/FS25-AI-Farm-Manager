# FS25 Game Guide — Index

An offline, source-cited reference for Farming Simulator 25 game mechanics, extracted from two
official manual PDFs. This resource exists so the skill's own references (`crop-calendar.md`,
`time-mechanics.md`, etc.) can *cite* game mechanics instead of asserting or inferring them (root
cause of frictions F-117/F-120/F-115).

**Sourcing history, kept for context:** this guide was originally built from the base
`FS25-manual_EN.pdf` (24pp) plus the FS25 Academy website. The Academy was subsequently found to
carry unrevised Farming Simulator 22 content (5 confirmed instances, see the punch list below,
mostly now resolved or discounted) and was **dropped as a primary source**. A newer, fuller,
confirmed-FS25-clean PDF — `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — became
primary, cross-checked against the base manual. Every file in this directory has been rebuilt or
re-verified against these two PDFs; no Academy claim is presented as fact anywhere in this guide
— genuinely useful but PDF-uncorroborated Academy content is kept only in clearly labeled
"Academy-sourced, unverified" notes, never as a citation-bearing fact.

**This guide is a token-lean, offline-readable distillation, not the live source of truth.** The
game's in-game Help menu is the authoritative, always-current reference — its content lives
inside GIANTS-encrypted archives and can't be parsed into this guide (confirmed: only the schema
is unpacked, not the text), so it can't be folded in directly, but it's the reference that wins
whenever it and this guide disagree, because it can't go stale the way a static copy can.
Per-topic files carry a one-line "see the in-game Help for the live version" pointer rather than
repeating this on every page.

## How this resource is built

- Every section cites its source: `FS25HF p.X` (primary) with a one-line `(base p.Y agrees)` note
  where a programmatic diff confirmed the two editions match; genuine differences are called out
  explicitly, never silently resolved.
- Manual text is extracted with PyMuPDF; dense data pages (crop/animal/production tables) are
  additionally **visually cross-checked** against the rendered page image.
- Zero-delta sections get a one-line "confirmed byte-identical" note rather than re-quoting both
  PDFs in full — the diff *is* the verification.
- Numbers, thresholds, and mechanics are quoted/curated, never invented or inferred. Where a
  source doesn't state something, the file says so explicitly ("Not covered on this page") rather
  than leaving a silent gap that looks like completeness.
- Where the two manual editions genuinely disagree, or a prior Academy-sourced claim conflicts
  with the manual, it's flagged in-place and in the punch list below — not silently resolved.
- This is a **living** resource — the coverage table below is the map of what's covered vs.
  explicitly out-of-scope; update it whenever a section is added.

## Coverage table

| Topic | File | Primary source | Status |
|---|---|---|---|
| Finances, Loans, Contracts, Passive Income | `finances.md` | FS25HF p.8 (base p.8 agrees) | ✅ done (incl. F-124 interest-accrual verdict) |
| Ground Working (liming, plow/cultivate, sow/plant, weeds, rolling, mulching, stones, fertilizing) | `fields.md` | FS25HF pp.11-12 (base agrees) | ✅ done |
| Crops (26-crop data table incl. Onions, storing, greenhouse, seasonal/weather) | `crops.md` | FS25HF pp.9-10, 13, 26 (base agrees except Onions + Oilseed Radish, see punch list) | ✅ done |
| Animal Husbandry (per-animal food/product, feed types, silage, TMR) | `animals.md` | FS25HF pp.14-15 (base agrees except Cows→"Cows & Highland Cattle") | ✅ done — Highland Cattle resolved (folded into Cows, not a separate animal) |
| Time & Calendar Settings (days-per-month/`daysPerPeriod`, timeScale, sleep, seasonal growth) | `time-and-settings.md` | Not in either manual PDF (confirmed by keyword scan) — re-grounded in the skill's verified `time-mechanics.md` instead | ✅ done — planning-critical: everything time-based scales with `daysPerPeriod`; re-grounded in verified game-file facts (not Academy) since no PDF covers this topic; the Academy's timeScale range was dropped as contradicted, daysPerPeriod's range/default kept only as an explicit unverified note |
| Forestry (tree types, planting, transport/sale, machines & tools) | `forestry.md` | FS25HF pp.16-17 (base agrees) | ✅ done — **Platinum-Expansion flag RESOLVED**: FS25HF confirms all 4 tools as real base content |
| Productions & Constructions (25-factory input/output table incl. 4 HF-only factories, construction projects, build menu) | `production.md` | FS25HF pp.18-21 (base agrees, HF adds 4 factories + fish-farming overview) | ✅ done — Onion-processing and Fish-Food gaps resolved with official data |
| Vehicles, Machines & Tools (AI workers, GPS-assist, configs, repair, icon glossaries) | `machinery.md` | FS25HF pp.22-23 (base agrees) | ✅ done |
| Getting Started / Controls / HUD / Mode Options / Maps / First Machines | `getting-started.md` | FS25HF pp.3-7 (base agrees except Maps: HF has 4 maps incl. Kinlaig) | ✅ done |
| Multiplayer & Mods | `multiplayer.md` | FS25HF p.27 (base p.24 agrees, content unchanged) | ✅ done |
| Fishing & Aquaculture | `fishing.md` | FS25HF pp.21, 24-26 — **not in the base manual at all** (confirmed HF-exclusive expansion content) | ✅ done — fully rebuilt from official manual text, not Academy; drops an unconfirmed Academy claim (species-specific fish-lake housing) |
| Installation | — | FS25HF p.2 | out of scope — not a gameplay mechanic |
| Highland Cattle | — | — | ⏹ **resolved, not a gap** — it's a name addition to the existing Cows entry (`animals.md`), not a separate animal |
| Game Basics (session setup, controls, HUD icons beyond p.5, AI helper intro) | — | Academy only | ⏹ **intentionally out-of-scope** — player onboarding/UI/controls, not farm-management decisions |

**Coverage is complete: every topic is either ✅ covered with a PDF citation or ⏹ explicitly
marked out-of-scope with a stated reason.** No row is left as an ambiguous "pending," and no
file retains an old-Academy-primary-pass banner.

## Needs in-game verification — the punch list

Every remaining genuine data ambiguity, consolidated into one list. These are the ones an actual
FS25 install can settle that reasoning about the sources further cannot. Several earlier flags
**resolved or discounted** during the FS25HF rebuild and are listed separately below, not here.

| # | Flag | Where | What's ambiguous | Practical takeaway |
|---|---|---|---|---|
| 1 | **Oilseed Radish's Avg. Selling Price + Harvested-during fields are missing in FS25HF** (present in the base manual: €1,596, Jan–Dec) | `crops.md` | Could mean Oilseed Radish is non-sellable/catch-crop-only in HF, or could be a content gap in the newer manual. | Verify in-game whether Oilseed Radish can still be sold/has a harvest window in the HF edition; don't assume the base manual's values still apply. |
| 2 | **Sugar Beet vs. "Sugar Beet Cut" — undefined distinction** | `production.md` | Both editions list them as separate deliverable goods (Sugar Mill/Biogas Plant inputs) with no explanation of what differentiates them. | Verify in-game whether "Sugar Beet Cut" is a processing byproduct, a different silo state, or something else. |
| 3 | **Pigs feed list — sorghum in prose, not in the icon table** | `animals.md` | Both manual editions' Pigs icon table omits sorghum; both editions' descriptive paragraph includes it. Not an HF-vs-base difference — both editions have the same internal inconsistency. | Treat sorghum as valid pig feed (the icon table looks like the incomplete side), but not 100% confirmed. |
| 4 | **"Silverrun Forest"** (named in `forestry.md`'s Yarder section, both editions) doesn't match any of FS25's 4 known maps (Riverbend Springs, Hutan Pantai, Zielonka, Kinlaig) | `forestry.md` | Since the manual itself is confirmed authentic FS25 content, this is likely a named forestry sub-location rather than a content-quality issue — but not confirmed. | Low stakes — not a trust concern, just an unconfirmed place name. |
| 5 | **`time-and-settings.md`'s `daysPerPeriod` range/default (1-28 days, default 1)** — still Academy-sourced, unconfirmed | `time-and-settings.md` | Neither manual PDF covers this topic; re-grounded in `time-mechanics.md`'s verified facts (12-period structure, mechanism) where possible, but the specific range/default figure has no verified source at all — kept only as an explicit unverified note, not fact. | Treat the range/default as unconfirmed; if it matters, that's an in-game settings-menu question, not something derivable from a save file. |

## Resolved or discounted during the FS25HF rebuild (no longer open questions)

- **✅ RESOLVED — 4 Forestry tools (Hydraulic Breaker, Tree Marking Spray, Yarders, Winches):**
  previously flagged as possibly FS22-Platinum-Expansion-only. FS25HF p.17 — confirmed FS25-clean
  — presents all 4 identically to the base manual, no expansion caveat. These are real base-FS25
  content; the Academy's claim about them was itself the bad information. See `forestry.md`.
- **✅ RESOLVED — Highland Cattle:** previously an open Academy-only sighting, unclear if a
  separate animal. FS25HF p.14 renames "Cows" to "Cows & Highland Cattle" — same entry, a breed
  addition, not a separate animal. See `animals.md`.
- **✅ RESOLVED — Onions' manual status:** previously flagged as "not one of the manual's 25
  crops," Academy-only. FS25HF confirms Onions as an official 26th crop with full data (p.10) and
  a full growing account (p.26): *"With onions, a new crop is introduced as well!"* See
  `crops.md`/`fishing.md`.
- **✅ RESOLVED — Onions/Fishing's "Kinlaig" map-scoping:** previously a lead, not confirmed.
  FS25HF confirms Kinlaig as the 4th official FS25HF map (p.4, p.26) and Highlands Fishing as a
  named expansion (p.24). Not a content-quality issue — genuine new content.
- **Discounted — Olives planting window:** previously flagged as a "real conflict" (manual
  Mar–Jun vs. Academy Aug–Sep). Both manual editions agree with each other on Mar–Jun; the
  conflicting claim was Academy-only, and the Academy is no longer trusted. Resolved in the
  manual's favor, not left open. See `crops.md`.
- **Discounted — 3 minor crop timing mismatches** (Potatoes, Green Beans, Peas): same treatment
  as Olives — Academy-vs-manual only, both PDF editions agree with each other, discounted.
- **Dropped entirely — the John Deere 7R/700M loader-compatibility note:** one of the confirmed
  FS22-tainted Academy claims (appeared identically in 2 separate Machinery 101 articles). Not
  even kept as an unverified note. See `machinery.md`.
- **Historical pattern, not an active flag — "stale FS22 copy" recurred across what is now 5
  confirmed instances** before the PDF pivot (Field Stones, the Academy's FS22 map list, the JD
  loader note ×2, the 4 forestry tools) — this pattern is *why* the Academy was dropped as a
  source, not something requiring further action itself.

## Verified consistency (cross-source agreement worth noting)

- Soil rolling's +2.5% yield figure appears identically in both manual editions (p.11) — a figure
  that also happened to match several now-deprioritized Academy articles, corroborating detail
  rather than conflicting with it.
- Liming's "every three harvests" interval is consistent across both manual editions.
- **24 of 26 crops' full data rows are byte-for-byte identical between FS25HF and the base
  manual** (confirmed by direct text diff, not spot-check) — only Onions (HF addition) and
  Oilseed Radish (HF data gap, see punch list) differ.
- `fields.md` (pp.11-12), `production.md`'s first 12 factories (p.19) and Construction Projects/
  Build Mode Menu content (p.21), `machinery.md` (pp.22-23), and `multiplayer.md` (p.24/27) are
  all confirmed byte-for-byte identical between editions — the HF edition is a strict superset,
  not a rewrite, everywhere except crops (p.9-10), animals (p.14), production (p.20-21 additions),
  getting-started (p.4 maps), and the new Highlands Fishing section itself.
