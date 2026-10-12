# Uninstall

Removing the Farm Manager does not touch your savegame. It never wrote anything there.

## Remove the mod

1. Close the game.
2. Delete `FS25_AIFarmManager25.zip` from your `mods` folder.
3. Optional: delete the mod's settings folder. It holds your panel position, your cards and
   the menu page's figures.

   ```
   Documents\My Games\FarmingSimulator2025\modSettings\FS25_AIFarmManager25\
   ```

## Remove the manager

1. End any running session.
2. Delete the four skill folders from your farm folder's `.claude/skills/`:
   `fs25-farm-manager`, `farm-briefing`, `farm-closeout`, `farm-status`.

## Your farm's memory

The `sanctum` folder in your farm folder is your farm's history and plans.

- **Keep it** if you might come back. A later install picks it up.
- **Delete it** to remove everything the manager remembered. This cannot be undone.

The `cache` folder beside it can always be deleted.

## What is left afterwards

Nothing in your savegame. Three things can remain elsewhere:

- **Claude Code's session history** for the farm folder. Claude Code keeps it outside the
  folder, and it holds what Cyrus read from your save. See Claude Code's own documentation
  to clear it.
- **A cache in another place**, if you ever set `paths.cache_dir` in `sanctum/config.json`.
- **A card file in another place**, if you ever used `--bridge` or the `FS25_BRIDGE`
  variable.

The full list of what is written, and where, is in
[Files on disk](../reference/files-on-disk.md).
