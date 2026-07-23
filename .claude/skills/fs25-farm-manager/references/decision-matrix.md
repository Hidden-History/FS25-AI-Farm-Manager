# Decision Matrix — always-check items by farming area

A growing, terse checklist: concrete things to verify before recommending or concluding
anything in a given area of FS25 farm management. **One short sentence per item, no
paragraphs.** This is not the general decision-weighing policy (that's
`references/decision-making.md`, prose, "how to weigh a contract/purchase/sale") and it is
not this farm's own risk appetite (that's `sanctum/identity/decision-making.md`). This file
is universal FS25/mod mechanics and verification habits — true for any save, not one farm's
judgment.

**When a new gotcha is discovered, add it immediately** as a bullet under its heading — or as
a new `##` heading if it doesn't fit an existing one. Newest entries can go anywhere sensible
within their heading; there's no required ordering within a section. Keep every entry a
single short sentence.

## Crop Planning

- Check a crop's actual windrow/harvest-output fillType before assuming it matches a
  building's input — don't infer from category (alfalfa → `alfalfa_windrow`, not
  `grass_windrow`; clover → `clover_windrow`, also not `grass_windrow`).
- `groundType` is terrain texture, not the crop or its readiness — read `crop_state` instead.
- A field's listed crop is a live read, not a durable fact — recheck immediately before a
  purchase, don't trust an earlier snapshot.
- A parcel's standing crop transfers free on purchase — a ready or growing crop is a reason
  to buy sooner, not a reason to wait.

## Land Purchase

- Confirm whether the map's land price is flat (a fixed rate × area) or scaled before
  assuming there's no timing play — check per map, it varies.
- A parcel's area/cost/current-crop are all genuinely readable — never ask the player for
  these, look them up.

## Production Chains

- A building can run multiple independent recipe lines in parallel, each fed by a different
  crop — check every accepted input, not just the first one delivered, before calling a
  building "fully utilized."
- Confirm a recipe's exact inputs/outputs from the mod's own XML before trusting a display
  name, a similarly-named building elsewhere, or a memory of "what this kind of building
  usually does."
- A DLC/packed building's full recipe menu may not be readable from disk at all — only what
  the save currently shows as `isEnabled`/active is confirmed; say so rather than guessing
  the rest from an unrelated stand-in file.
- Never use one placeable's file as a stand-in reference for a different placeable just
  because the filenames look similar — verify against the actual owned instance's own save
  data before repeating the guess as fact.
- If in-game evidence (menu listing, money actually charged) contradicts what the save file
  shows, trust the player's direct observation over the file — but say so plainly and keep
  investigating why the file disagrees, don't just paper over the gap.

## Husbandry & Animal Feed

- Feed effectiveness varies by fillType (e.g. one may be 100% effective, others partial) —
  confirm which fillType is the animal's real intended food, don't assume any "food-like"
  fillType is equivalent.
- Check the specific husbandry building's own file for its actual accepted inputs — don't
  assume a differently-named or similarly-purposed building needs the same thing.
- Confirm a husbandry building actually exists for an animal before planning its feed chain —
  a feed mixer producing the right output doesn't help if there's nowhere to house the animal.
- Feed production/stockpile before any animal purchase — sequence it, don't buy livestock on
  the promise of feed that isn't flowing yet.

## Equipment & Mods

- A mod placeable with no `.lua` script relies entirely on the base game's generic save/load
  path — a persistence bug there is more likely a malformed/incomplete XML field than custom
  broken logic.
- When a mod's save-behavior looks buggy, structurally diff its placeable XML against a
  known-working placeable of the same type (`<storeData>` fields present/missing, tag casing)
  before concluding it's unfixable.
- A vehicle's actual accepted fruit types live in its own `<cutter fruitTypes="...">` (or
  equivalent) tag — don't infer capability from a store category label or a real-world brand
  association.

## Investigation Method

- Re-run a script fresh against the current save before concluding it "can't find" something —
  don't consult an earlier cached read and mistake staleness for a capability gap.
- An internal file path or mod folder name is not the in-game display name — never present an
  invented label as confirmed without flagging it as a guess, and ask what the player actually
  sees on their screen when it matters.
- When two things share a theme (e.g. two "onion" buildings), verify recipe details actually
  match before assuming a new report describes the same object already being discussed.
