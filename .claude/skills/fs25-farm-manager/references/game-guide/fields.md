# Fields & Ground Working

**Sources:** `FS25HF-manual_EN.pdf` ("Highlands Fishing" edition, 27pp) — **primary**, pp.11-12
("Ground Working"). Cross-checked against `FS25-manual_EN.pdf` (base edition, 24pp), same pp.11-
12: **programmatically confirmed byte-identical** — no content changes between editions on this
topic. Academy "Ground Working 101" content that was previously folded into this file has been
**re-verified against both PDFs** per the corrected sourcing policy (the FS25 Academy website
carries unrevised Farming Simulator 22 content and is no longer a primary source). Only Academy
facts corroborated by a PDF are presented as fact; genuinely useful uncorroborated Academy facts
are kept in clearly labeled "Academy-sourced, unverified" notes; FS22-tainted Academy content
(the Field Stones article) has been dropped entirely.

**This file is a distillation, not the live source of truth** — see the in-game Help for the
live version of this content.

## Field Info Box & Map Filters

**Academy-sourced, NOT in either FS25 manual — unverified.** ([Academy: Introduction to
Fields](https://farming-simulator.com/newsArticle.php?news_id=290), not one of the confirmed
FS22-tainted articles, but not corroborated by either PDF either — kept as a plausible, useful
note rather than presented as manual fact.)

Standing on a field reportedly shows a context-sensitive info box (lower right) with: Owned by,
Crop type, Growth, Yield bonus, Fertilized (up to two applications to reach 100%), Weed stage
(small/medium/large), and whether liming/rolling/plowing is needed. The map screen reportedly has
matching filters (crop type, growth, soil composition). Not verified against a PDF or the in-game
Help — treat as directionally useful, not confirmed exact.

## Liming

**Sources:** FS25HF p.11 (base p.11 agrees, confirmed identical).

- Lime increases yield; apply with a fertilizer spreader (spreaders that support it show a lime
  icon).
- **Required after every third harvest**, per the field info.
- Apply lime *before* plowing/cultivating, which works the lime into the soil.

### What `limeLevel` means in the save (FM-1001 item 6 — from game data and engine source, not the manual)

- **`limeLevel` in `fields.xml` is the field's lime state, a whole number from 0 up.** The map's
  own `fieldGround` config declares the lime layer with `numChannels="2"` (the base `mapUS`, `mapEU`
  and `mapAS`, and many map mods, all do), which holds the values 0 to 3; a save from such a map
  shows only 0, 1, 2 and 3. Read the layer's `numChannels` from the map's own
  `config/fieldGround.xml` (`<limeLevel … numChannels=>`) rather than assuming 3 is the top on
  another map.
- **0 is the deficit end: it is the state the game's own soil map paints as "needs lime"**
  (`MapOverlayGenerator.lua`, the `NEEDS_LIME` filter colours limeLevel state 0), and only when
  the career setting `limeRequired` is true (`careerSavegame.xml` `<limeRequired>`). With
  `limeRequired` false the game does not ask for lime and a 0 means nothing needs doing.
  Higher is better supplied; spreading lime raises the value (`read_fields.py` measured four of five
  upward moves coinciding with `sprayType` going to LIME).
- **When a field needs lime:** its `limeLevel` is 0, `limeRequired` is true, and the crop you
  plan to sow asks for it. Each crop's own foliage file carries `growthRequiresLime` and
  `consumesLime`; most base-game arable crops set both true; grass, the meadows, rice and long-grain
  rice set both false, and oilseed radish sets `consumesLime` false (`data/foliage/*/*.xml`). A map or mod crop can differ, so read the crop's own file.
  Say "needs lime before sowing" for a 0 on a field going to a lime-requiring crop. For a field
  going to grass, say what the crop file says (it sets both flags false) and that the engine's own
  reading of those flags is native — the engine's readable source reads an attribute spelled
  differently from the one these files carry — so an in-game check settles it.
- **The spreading rate is not one fixed number.** The game's lime figure is 0.09 L per second
  (`data/maps/maps_sprayTypes.xml`, `LIME litersPerSecond`), and a sprayer uses
  `scale × litersPerSecond × speedLimit × workingWidth × dt × 0.001`
  (`Sprayer.lua`, `getSprayerUsage`), so litres per hectare depend on the machine's own
  `usageScales` and on how fast it is driven. For a machine at its speed limit that works out to
  about 3,240 L per hectare times the machine's usage scale — a figure derived from those two
  lines, not one the game prints. For a real farm, quote it as derived, or read the machine's own
  `usageScales` in its XML.
- **Not in the readable engine source, so do not state them:** how many levels one spreading adds,
  how much a harvest takes off, and what a level is worth in yield (the lime factor goes into a
  native harvest multiplier). If the player needs one, say it is not documented and suggest
  watching the field's level across one spreading or one harvest.

## Plowing & Cultivating

**Sources:** FS25HF p.11 (base p.11 agrees, confirmed identical).

- **Plowing** turns the soil, going deep; **cultivating** only loosens the top layer.
- Plowing is required after harvesting root crops and at regular intervals otherwise you lose
  profit.
- Plows can create/combine/expand fields and prevent weeds from growing. Subsoilers are a
  cheaper/faster alternative but cannot create fields or prevent weeds.

**Academy-sourced, NOT in either FS25 manual — unverified.** A per-tool driving-speed/effect
comparison (regular plow 12kph/creates fields/prevents weeds; spader 5-8kph/no weed prevention;
subsoiler 12-15kph/no field creation/no weed prevention; cultivators 15kph; disc harrow 18kph;
power harrow 12kph) was previously sourced to Academy news_id=294. Not corroborated by either PDF
— dropped from the factual sections above; noted here only as a pointer that such detail may
exist in-game (see the in-game Help) but isn't confirmed by this guide's sources.

## Sowing & Planting

**Sources:** FS25HF p.11 (base p.11 agrees, confirmed identical).

- Seeders and planters are used depending on crop (see `crops.md`'s per-crop table for which
  applies).
- Check the crop calendar for the appropriate sowing window for each crop.
- Fill the machine with seeds from a bag, pallet, or silo before sowing.

## Getting Rid of Weeds

**Sources:** FS25HF p.12 (base p.12 agrees, confirmed identical).

- Three weed growth stages: **small → medium → large**.
- Weeders remove small weeds mechanically; hoes handle medium weeds (and small); a weeder
  "can't be used with crops that are planted in rows (e.g. potatoes)" — use a hoe there instead.
- Sprayers/herbicide are the last resort for large weeds; work on smaller weeds too, but the
  herbicide application itself carries a yield penalty.

### Which tool does what to which weed level (FM-1001 item 5 — the game's own table, which wins over the manual's wording above)

**The "weed level" is `weedState` in `fields.xml`: the same number the game's weed tables are
written in.** (`FieldState.weedState`; `Weeder.lua` builds the weeder's requirement from the weed
system's replacement table keyed by those source states.) 0 means no weeds. Speak in this number
and never in "small, medium, large": the manual's three words are a gloss, not a mapping.

What the base game's `data/maps/maps_weed.xml` says each tool does to a state (a bare "→ N" is a
move to state N; "→ 0" is no weeds):

| weedState | Grows to | Weeder | Hoe | Herbicide | Mulcher |
|---|---|---|---|---|---|
| 1, 2 | 3, 4 | → 0 | → 0 | → 0 | no row |
| 3 | 4 | → 0 | → 0 | → 7 | → 0 |
| 4 | 5 | → 6 | → 0 | → 8 | → 0 |
| **5** | stays 5 | no row | no row | → 9 | → 0 |
| 6 | stays 6 | no row | → 0 | → 7 | → 0 |
| 7, 8, 9 | stay | no row | no row | no row | → 0 |

"No row" means the file gives that tool no action on that state. What the file does **not** say,
and nothing readable does:

- **Whether a state the herbicide moves a weed to (7, 8, 9) still costs yield.** The game's field
  info (`fieldInfoStates` in the same file) labels only states 1 to 6; states 7 to 9 carry no
  label. The file lists a `factor` per state (3: 0.5, 4: 0.75, 5: 1.0, 6: 0.5, 8: 0.5, 9: 0.75; none
  for 7) that the engine passes into the harvest multiplier, but that multiplier is native code, so
  no yield percentage may be derived from it and nothing here may be said about what a sprayed field
  loses. Do not say herbicide "does not work" or "does not clear" a state, and do not tell the player
  to avoid it: say what the table says (it moves state 5 to 9), that whether 9 still costs yield is
  not known, and that an in-game test (spray one field, read the field info afterwards) settles it.
- **Which tool a state "wants".** The table gives what each tool does; choosing among tools is a
  judgement the player shares, with the crop's own gate below.

Plain reading of the table, for the states that matter most:

- **At weedState 5 a weeder pass and a hoe pass have no row in the file**, herbicide moves it to 9,
  and the mulcher is the only tool the file sends to 0. State 5 is the end of the growth chain
  (3 → 4 → 5, no further), which is why acting at 4 or below is the cleaner window. For fully grown
  weeds the tool the table acts on, besides the mulcher, is herbicide; the game's own manual
  (FS25HF p.12, above) says herbicide carries a yield penalty, and **neither the manual nor any
  readable data gives its size** — say it costs some yield and that the size is not known.
- **A mulcher destroys a standing crop.** On a field with a crop standing, never offer mulching as
  weed control without saying so in the same sentence: it is the harvest-or-sacrifice decision, not a
  routine pass. The field's weed verdict carries a `standing_crop_warning` in that case.
- **The crop gates the tool as well.** A crop's foliage file allows weeding or hoeing only at certain
  growth states, so a row that says "→ 0" can still be unavailable on a field with a crop in it.
  `read_fields.py` applies both and reports the blocked tools with the reason.
- **A map may carry its own table.** The map's weed file is the `<weed filename=>` named in the map's
  own config. Many maps' files hold only the info-layer wiring, so the base table above is the one in
  force; some maps ship `<replacements>` of their own for particular fruit types.
  `read_game_defs.py` reads the map's file first and the base file second and records which one it
  used (`weed_model_source`). Where a map's file declares replacements, the readable engine source
  does not show whether they add to or replace the base table (the weed system is native), so say
  which file the answer came from and ask the player to confirm one tool in the game.

**How the manager answers:** for every field with weeds, take the field's own `weeds` operation
(`operations_this_state_calls_for` in the field state, `operations` in `field_work`). Offer the tools
in its `detail.clearing_tools` (those the table sends to 0), with `standing_crop_warning` if present.
**For fully grown weeds (weedState 5), where `clearing_tools` is only the mulcher, also offer herbicide**
(duty D-04): it moves state 5 to 9 (`detail.tools_that_move_it_to_another_state`, `moves_state_to`) at a
yield cost of unknown size, per the unknown above. Under that key list what every tool does, never as a
do-not-send list and never as a claim that the field is or is not still weedy. If `clearing_tools` is empty, say what `reason` says. Do not substitute a tool
because the farm happens to own one. Whether the farm owns a sprayer is still unknown to the save
(the existing rule stands).

**Academy-sourced, NOT in either FS25 manual — unverified.** A "+20% yield if your harvest is
weed-free" figure was previously sourced to Academy news_id=293. Not corroborated by either PDF —
genuinely useful if true, but not presented as fact here; verify in-game before relying on it.

## Soil & Grass Rolling

**Sources:** FS25HF p.11 (base p.11 agrees, confirmed identical).

- **Soil rollers**, used after sowing on a cultivated field, condense the soil for a **+2.5%
  yield** bonus (both manual editions state "2,5%" identically) and press small stones back into
  the ground so they don't damage the harvester later.
- **Grass rollers** are used after mowing; rolling cut grass prepares it for the next growth
  cycle and automatically grants a fertilizing stage.

**Academy-sourced, NOT in either FS25 manual — unverified.** The detail that rolling over
*matured* (unmowed) grass resets its growth stage, rather than granting the fertilizing stage,
was previously sourced to Academy news_id=295. Not corroborated by either PDF.

## Mulching

**Sources:** FS25HF p.12 (base p.12 agrees, confirmed identical).

- Mulching applies cut biological material to the soil; the manual describes it as improving
  yield ("Improves Yield!") but **does not give a numeric bonus in either PDF edition** —
  confirmed by direct text search of the full FS25HF text for "2,5%" (only 1 occurrence in the
  whole document, the Soil Rolling figure above — mulching's is not one of them).
- Usable on any crop that leaves stubble: wheat, barley, oat, sorghum, sunflowers, soybeans, corn.
  Use it **after harvesting, before cultivating**.
- For grapes/olives, mulch **after** cultivating instead (to cut back regrowing grass and avoid a
  weed yield penalty).

**Academy-sourced, NOT in either FS25 manual — unverified.** A "+2.5% yield bonus on the next
harvest" figure for mulching specifically was previously sourced to Academy news_id=296 and
directly confirmed absent from both PDFs (searched, not assumed). If this number matters for a
management decision, verify in-game rather than trusting this guide's old Academy citation.

## Getting Rid of Stones

**Sources:** FS25HF p.11 (base p.11 agrees, confirmed identical).

- Stones (mentioned generically, sizes not itemized in this section's manual text beyond the
  general mechanic) appear from plowing/cultivating; smaller stones can be removed with a roller,
  bigger stones need to be collected with a stone picker and sold at the debris crusher.

**Dropped from this file:** a previous pass sourced additional stone-size detail (three sizes:
small/medium/large, with color-coded map filters) to Academy news_id=318 ("Field Stones"). That
article is one of the **confirmed FS22-tainted** sources (it literally states "In Farming
Simulator 22, field stones appear in three sizes...") and has been dropped entirely per the
corrected sourcing policy — not because the mechanic is necessarily wrong, but because this
specific source can no longer be trusted and neither PDF corroborates the three-size breakdown
independently. If the three-size mechanic matters, verify in-game.

## Fertilizing

**Sources:** FS25HF p.12 (base p.12 agrees, confirmed identical).

- Fertilize at least once per crop cycle; **up to two applications**, with a growth stage
  required between them, to reach 100%.
- Fertilizer types: solid (spreader), liquid (sprayer), slurry (from cows/pigs, needs an
  underground tank + fresh water for the animals), manure (from cows/pigs, needs straw bedding +
  water), digestate (free byproduct of selling manure/silage at the biogas plant, applied like
  slurry), and catch crops (oilseed radish — cultivate it over once grown for one fertilization
  stage, then plant the real crop).
- Manure/slurry spreaders support a "double activation rate" to fertilize to 100% in one pass.

**Academy-sourced, NOT in either FS25 manual — unverified.** Two details — grass can only be
fertilized once (not twice), and the double-activation-rate trades half the normal application
speed — were previously sourced to Academy news_id=292. Not corroborated by either PDF.

## Harvesting & Transporting

**Sources:** FS25HF p.12 (base p.12 agrees, confirmed identical).

- Check the crop calendar for the correct harvest window; growth stage is visible in the field
  info box or on the map.
- Use a harvester with the crop-appropriate header attached.
- If the combine's tank is full, unload into a trailer; transport to a selling point, factory,
  or storage. Different trailer types exist for solid crops, liquids, logs, livestock, etc.

## Yield-improvement figures at a glance

Only PDF-confirmed figures are presented as fact; Academy-sourced figures are marked unverified.

| Action | Stated bonus | Status |
|---|---|---|
| Soil rolling | +2.5% | **PDF-confirmed** — FS25HF p.11 = base p.11 |
| Mulching | ~~+2.5%~~ | Academy-sourced, unverified — absent from both PDFs |
| Weed-free harvest | ~~+20%~~ | Academy-sourced, unverified — absent from both PDFs |
| Liming | Not quantified | Both PDF editions call it necessary for full yield, neither gives a % |
| Fertilizing to 100% | Not quantified | Both PDF editions call it important, neither gives a % |

## Not covered on these pages

Neither PDF edition gives: a numeric yield-bonus for liming, fertilizing, or mulching; a
weed-free yield bonus; per-tool driving speeds; or seed pricing. None of these are asserted here
as manual fact — see the Academy-sourced unverified notes above for what a prior (now-corrected)
pass had claimed.
