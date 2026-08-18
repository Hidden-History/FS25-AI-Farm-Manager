---
name: o1-bind-save
description: 'Find the saves, bind to exactly one slot, and ask only for the install and mods directories the disk cannot infer.'
nextStepFile: './o2-present-position.md'
---

# O1: Bind the save

**Progress: Step 1 of 5** — Next: Take delivery and present the position

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
