# Update to a newer version

Update **both halves together**. The mod and the manager from different releases do not
match: the menu page reads files the manager writes, and their format moves between
releases.

## Steps

1. **Close the game** and end any running manager session (`/farm-closeout`).
2. **Back up your farm folder.** Copy the whole folder somewhere safe. Your `sanctum` folder
   is the part that matters.
3. **Replace the mod.** Delete the old `FS25_AIFarmManager25.zip` from your `mods` folder and
   copy the new one in. Keep exactly one copy. Do not keep the old zip in `mods` under
   another name: the game would load both.
4. **Replace the four skill folders** in your farm folder's `.claude/skills/`:
   `fs25-farm-manager`, `farm-briefing`, `farm-closeout`, `farm-status`. Delete the old four
   and copy the new four in.
5. **Leave `sanctum` alone.** It is your farm's memory and it carries over. On the first
   briefing after an update the manager may rearrange files inside it to match the new
   version. It makes a dated backup under `sanctum/history/archive/` first and tells you
   in one line what it changed.
6. Start the game, load your savegame and save once.
7. Start a session (`/farm-briefing`). The manager re-reads your save and refreshes the
   menu page.

If you have more than one farm folder, repeat steps 4 to 7 in each.

## What changes when you come from 3.0.0.0 or older

- **Cards you had not dismissed are cleared once.** Older versions kept one card list for
  every savegame, so the old cards cannot be matched to a savegame.
- **Answers the manager had not yet read are discarded once**, for the same reason.
- Your panel position and settings are kept.

After that, each savegame keeps its own cards and answers.

## Check it worked

- The mod list shows the new version number for **AI Farm Manager 25**.
- After the first save with a session running, the Farm tab's "as of" time is today's.

If the Farm tab still shows old figures, see
[Troubleshooting](troubleshooting.md#the-menu-page-shows-old-numbers).
