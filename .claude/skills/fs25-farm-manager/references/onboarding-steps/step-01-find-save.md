---
name: step-01-find-save
description: 'Find the save with locate_save.py, bind to exactly one slot, then ask only for the install and mods directories the disk can''t infer.'
nextStepFile: './step-02-read-everything.md'
---

# Step 1: Find the save, then ask only for what's left

**Progress: Step 1 of 7** — Next: Read everything

**Find the save, then ask only for what's left.** Run `locate_save.py` with no arguments —
it auto-detects WSL, native Windows, and every install layout it knows about
(`FRICTION-LOG.md` F-007, now fixed), and lists the slots it finds with farm names and
mtimes:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/locate_save.py"
```
Show the player the slots; have them confirm which one this manager is for — **only ever
bind to one**. Only if the search comes back empty should you ask for the path, or point
`locate_save.py "<path>"` at their saves root.

Then ask for the two directories it doesn't cover: their **game install** (base-game store
prices) and their **mods** directory (modded prices, and this map's own config). Record all
three in `sanctum/config.json` under `paths` (`savegame_dir`, `install_dir`, `mods_dir`) —
`read_store_prices.py` and `read_farmland_areas.py` read that block, so getting it right
here is what spares the player every future price question.

## Next

Once the save is found and bound, read fully and follow: {nextStepFile}
