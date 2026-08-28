---
name: o4-bridge-check
description: 'Confirm the AI Farm Manager 25 mod is installed and sound — look, don''t ask; and never let its absence block onboarding.'
nextStepFile: './o5-write-sanctum.md'
---

# O4: Check the notification bridge

**Progress: Step 4 of 5** — Next: Write the sanctum and confirm ready

**Check whether the notification mod is installed — don't ask, look.** It is optional, and the
manager works fully without it.

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/notify_farm_manager.py" --path-only x
```

Then check for `FS25_AIFarmManager25.zip` in the profile's `mods/` folder. If it is there, confirm it
is actually **sound** — a present-but-broken zip means notifications are not really available, and
reading exit `2` at send time would look identical to "the game is closed" (F-029/F-030):

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/check_mods.py" "<mods_dir>" --mod AIFarmManager25
```

## ⛔ `notifications.available` is true only if BOTH hold

Record the answer in `config.json` as `notifications.available`: **true only if the zip is present
AND `check_mods.py` reports `status: "ok"` for it.**

If the zip is present but the report is `status: "issues"` (a missing or unopenable `modDesc.xml` is
a verified cannot-load), **set `notifications.available` to `false` and note the reason.** The mod is
installed but the game won't load it, so treat it as unavailable until it's fixed. **Present is not
the same as working**, and recording "present" as "available" is what makes a later silent failure
unreadable.

Optional, not every onboarding: dropping the `--mod` filter runs `check_mods.py` over the whole
`mods/` folder, which catches *any* structurally broken mod before a long session discovers it (its
purpose, F-122). Offer it if the player suspects a mod isn't loading; `read_game_log.py` reports
which mods the game actually failed to load.

## Absence never blocks onboarding

If it is **not** installed, say so once, plainly, and move on:

> *"I can also put messages on your screen while you play — that needs the AI Farm Manager 25 mod,
> which isn't installed. Say the word if you want it."*

**Do not sell it, and never let its absence block onboarding.** Everything else the manager does
works without it.

## Next

Once the notification state is recorded, read fully and follow: {nextStepFile}
