# Files on disk

This page lists where the Farm Manager writes.

## The promise

**The Farm Manager writes nothing into your savegame folder.** It reads your save files and
never changes, adds or removes a file there.

By default everything it writes is in two places: the mod's settings folder and your farm
folder. The exceptions are listed under [Other places](#other-places).

## 1. The mod's settings folder

```
Documents\My Games\FarmingSimulator2025\modSettings\FS25_AIFarmManager25\
├── state.xml                 panel position and panel on/off
├── settings.xml              optional, written by you (see below)
└── savegame1\                one folder per savegame, named like the savegame folder
    ├── notify.xml            a card on its way to the screen
    ├── cards.xml             the cards for this savegame
    ├── replies.xml           your answers, waiting for the manager
    ├── contracts.xml         contract rewards, read from the running game
    ├── farm.xml              figures for the Farm tab
    ├── fields.xml            figures for the Fields tab
    └── productions.xml       figures for the Productions tab
```

| File | Written by | Read by | Notes |
|---|---|---|---|
| `state.xml` | the mod | the mod | Shared by all savegames, because it describes your screen, not a farm. |
| `settings.xml` | you | the mod | Optional. |
| `notify.xml` | the manager | the mod | The mod deletes it once it has shown the card. That deletion is how the manager knows the card arrived. |
| `cards.xml` | the mod | the mod | Keeps unanswered cards across a restart. |
| `replies.xml` | the mod | the manager | The manager empties it after reading. |
| `contracts.xml` | the mod | the manager | The game does not save an offered contract's reward, so the mod writes it here. |
| `farm.xml`, `fields.xml`, `productions.xml` | the manager | the mod | Rewritten when you save with a session running. |

The savegame folder inside `modSettings` exists only once the game has been saved at least
once. On a new game that was never saved, the mod keeps no cards and no answers. It still
writes `state.xml`.

## 2. Your farm folder

```
my-farm/
├── .claude/skills/     the manager itself. Never holds your farm's data
├── sanctum/            your farm's memory: plain text, yours to read and edit
└── cache/              the manager's last verified read of your save. Safe to delete
```

`sanctum` also holds three small files the manager keeps for itself: `watch.pid` and
`watch-marker.json` (the background watcher) and `fleet-alert-state.json` (which fleet
alerts were already sent).

## Other places

- **Claude Code's own session history.** Claude Code keeps a record of your sessions outside
  the farm folder. It contains what Cyrus read from your save during those sessions. It
  belongs to Claude Code, not to the Farm Manager; see Claude Code's own documentation for
  where it is and how to clear it.
- **A cache somewhere else**, only if you set `paths.cache_dir` in `sanctum/config.json`.
- **A card file somewhere else**, only if you pass `--bridge` to the notifier or set the
  `FS25_BRIDGE` environment variable.

## What is read, and never written

- Your savegame folder, for example `savegame1\`.
- Your game install folder, for shop prices and map data.
- Your mods folder, for the prices and data of the mods you use.
- The game's `log.txt`.

## What leaves your PC

The Farm Manager's scripts send nothing anywhere. Two things do involve the network, and
both are outside those scripts:

- **Claude Code** talks to the AI model you have set it up with. What you and Cyrus say in
  a session, including what it read from your save, goes to that model.
- **Issue reports** go to GitHub only when you approve each one. See
  [Privacy and feedback](privacy-and-feedback.md).

## settings.xml (optional)

**Most players should use the [Settings tab](../how-to/in-game-menu.md#settings-tab) and
ignore this file.**

The mod reads `settings.xml` first and `state.xml` second, and `state.xml` wins. On every
exit the mod saves the panel's position, size, width, text size, opacity, both timings, the
retention and the minimum severity into `state.xml`. So once you have run the game once,
almost nothing in `settings.xml` has any effect. The one value `state.xml` does not carry
is `timing#msPerChar`.

If you want the file's other values to apply, close the game, delete `state.xml` (this
resets your panel position, the panel ON/OFF choice and your Settings tab choices), then start the game. This route
follows from how the two files are read; it has not been tried in game.

```xml
<farmManager25>
    <hud anchorX="0.985" anchorY="0.86" widthPx="330" textSizePx="13" bgAlpha="0.92" scale="1.0" />
    <timing minMs="8000" maxMs="60000" msPerChar="70" />
    <messages retain="50" minSeverity="info" />
</farmManager25>
```

| Attribute | Meaning |
|---|---|
| `hud#anchorX`, `hud#anchorY` | Where the panel sits, as a fraction of the screen (0 to 1) |
| `hud#widthPx` | Panel width in pixels |
| `hud#textSizePx` | Card text size in pixels |
| `hud#bgAlpha` | Card background opacity, 0 to 1 |
| `hud#scale` | Overall panel size. Values outside 0.4 to 1.5 are pulled back into that range |
| `timing#minMs`, `timing#maxMs`, `timing#msPerChar` | How long a card stays up when the panel is OFF: per character, with a floor and a ceiling |
| `messages#retain` | How many past messages to keep |
| `messages#minSeverity` | Lowest severity shown: `ok`, `info`, `warn` or `critical` |

What you set in the Settings tab or by dragging the panel is saved in `state.xml` and wins
over this file, as described above.
