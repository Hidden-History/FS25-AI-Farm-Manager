---
name: o1-bind-save
description: 'Ask the player''s name and language FIRST, then find the saves, bind to exactly one slot, and ask only for the install and mods directories the disk cannot infer.'
nextStepFile: './o2-present-position.md'
---

# O1: Bind the save

**Progress: Step 1 of 5** — Next: Take delivery and present the position

## First, before anything else — who are you, and what language?

⛔ **These two questions come before every command in this workflow, including `locate_save.py`.**
They need no save data, so nothing blocks them — and everything after this point is *spoken*, so
asking later means speaking the wrong language until you do.

1. **What should I call you?** — record as `player_name`.
2. **What language would you like me to speak?** — record as `language`.

⭐ **From their answer onward, speak that language** — the rest of this step, O2's position
briefing, O3's interview, O4, O5, and every session after.
`config.json`'s `language` is what carries it past today; a preference nothing reads is why
session 2 reverts to English.

⚠ **Any answer is an answer.** *"Just call me farmer"* is a complete reply — record it as given.
Never read the name from the save: `farms.xml`'s `lastNickname` is the OS account name (`"pc"` on a
default Windows install), a filesystem accident of exactly the class `build_header` already refuses
for `farm_name`. And the save carries **no language or locale attribute at all**, so this one cannot
be read from disk under any circumstances.

⛔ **ASK FIRST, THEN WRITE — never write a placeholder to correct later.** Until the player has
answered, `player_name` and `language` must be **ABSENT from `config.json`, not present as
`"unknown"`.** Writing `"unknown"` and updating it afterwards satisfies nothing and hides
everything: `sanctum_maintain check` classifies `"unknown"` as unanswered, but it only runs at the
END of onboarding, by which time the value has been overwritten — so the write-then-confirm is
invisible to every gate. **Absence is the detectable state.** This is the same defect the farm-name
step exists to prevent, and it must not be re-introduced on these two keys.

⚠ **Why this is allowed to precede the position (F-010).** F-010's rule is that the position
precedes every **judgment** question — the ones whose answers are only meaningful once the player
has seen their real farm. **A name and a language are identity DATA, not judgments**: nothing in the
save informs them and no briefing could change the answer. **This exemption covers `player_name` and
`language` and nothing else**; every judgment question still waits for O2.

## Then find and bind the save

**Find the save, then ask only for what's left.** Run `locate_save.py` with no arguments — it
auto-detects WSL, native Windows, and every install layout it knows about (`FRICTION-LOG.md` F-007,
now fixed), and lists the slots it finds with farm names and mtimes:

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/locate_save.py"
```

Show the player the slots; have them confirm which one this manager is for — ⛔ **only ever bind to
one.** A manager bound to two saves has no answer to "what is the farm's cash", and every file it
writes afterwards is ambiguous. Only if the search comes back empty should you ask for the path, or
point `locate_save.py "<path>"` at their saves root.

**Then bind the farm within that save.** The chosen slot's `farms` list (from `locate_save.py`)
carries `{farm_id, name}` for every farm on it — a multi-farm or joined-MP save can have more than
one. **One entry → use its `farm_id`.** **More than one → ask the player which farm is theirs, by
name**, and record the `farm_id` of the one they name. Every parser takes `--farm-id`, and it is
never inferred silently: an unrecorded `farm_id` here is exactly what lets a later read return
another farm's position, with no error key, on any save that isn't single-farm.

**Then ask for the two directories it doesn't cover** — and only those two: their **game install**
(base-game store prices) and their **mods** directory (modded prices, and this map's own config).
**Ask only for what the disk genuinely cannot infer**; everything else on this farm is read, not
requested.

Record the three directories in `sanctum/config.json` under `paths` (`savegame_dir`, `install_dir`,
`mods_dir`) — `read_store_prices.py` and `read_farmland_areas.py` read that block, so getting it
right here is what spares the player every future price question. Record `farm_id` at the top
level — `farm_snapshot.py` and every parser that filters by ownership take `--farm-id`, and this
step is what supplies it.

## Next

Once the save is found and bound to exactly one slot, read fully and follow: {nextStepFile}
