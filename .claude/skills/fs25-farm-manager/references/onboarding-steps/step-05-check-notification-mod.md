---
name: step-05-check-notification-mod
description: 'Check whether the notification mod is installed — look, don''t ask; record notifications.available; never let its absence block onboarding.'
nextStepFile: './step-06-write-sanctum.md'
---

# Step 5: Check whether the notification mod is installed

**Progress: Step 5 of 7** — Next: Write the sanctum

**Check whether the notification mod is installed** — don't ask, look. It is optional, and
the manager works fully without it.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/notify_farm_manager.py" --path-only x
```

Then check for `FS25_AIFarmManager25.zip` in the profile's `mods/` folder. If it is there,
confirm it is actually **sound** — a present-but-broken zip means notifications are not
really available, and reading exit `2` at send time would look identical to "the game is
closed" (F-029/F-030):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check_mods.py" "<mods_dir>" --mod AIFarmManager25
```

Record the answer in `config.json` as `notifications.available`: **true only if the zip is
present AND `check_mods.py` reports `status: "ok"` for it.** If the zip is present but the
report is `status: "issues"` (a missing/unopenable `modDesc.xml` is a verified cannot-load),
set `notifications.available` to `false` and note the reason — the mod is installed but the
game won't load it, so treat it as unavailable until it's fixed.

Optional, not every onboarding: dropping the `--mod` filter runs `check_mods.py` over the
whole `mods/` folder, which catches *any* structurally broken mod before a long session
discovers it (its purpose, F-122). Offer it if the player suspects a mod isn't loading;
`read_game_log.py` reports which mods the game actually failed to load.

If it is **not** installed, say so once, plainly, and move on: *"I can also put messages on
your screen while you play — that needs the AI Farm Manager 25 mod, which isn't installed.
Say the word if you want it."* Do not sell it, and never let its absence block onboarding.

## Next

Once the notification mod state is recorded, read fully and follow: {nextStepFile}
