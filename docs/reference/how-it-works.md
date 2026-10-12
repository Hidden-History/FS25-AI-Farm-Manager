# How it works

## Two halves, one loop

```
Claude Code (the manager)                     FS25 (the mod)

  reads your save
  decides something is worth saying
  writes a card ───────────────────────────►  shows it on the panel
                                              you click an answer
  reads your answer ◄───────────────────────  writes the answer

  you save the game  ◄──────────────────────  (the game writes your save)
  re-reads your farm
  writes the tab figures ──────────────────►  the menu page shows them, with the time
```

The two halves never talk directly. They pass small files through the mod's settings
folder. See [Files on disk](files-on-disk.md).

## The manager reads; scripts do the reading

Cyrus does not work your farm's numbers out in conversation. Dedicated scripts read your
save and write a checked copy to the `cache` folder. Cyrus reads that copy. A script that
cannot find its data reports an error; it does not return an empty answer that could be
mistaken for "you own nothing".

## The watcher

A briefing starts a small background watcher. It checks two files about once a second:
your savegame's main file and the answers file.

- **You save the game** → the watcher runs the refresh itself. The cache and the three tab
  files are rewritten.
- **You answer a card** → the watcher wakes Cyrus, who reads the answer and responds.

Between those events it costs next to nothing. Closeout stops it.

It checks the files on a timer because, under WSL, Linux cannot be told when a Windows
program writes a file.

## Why some figures are LIVE and others are "as of"

The mod can see the running game, so money and contracts on the Farm tab are **LIVE**.
Land, fleet, production and field figures come from your saved game through the manager,
so they carry an **as of** time: the moment the manager last read your save.

## If the panel cannot draw

The mod falls back in two steps, so a message is not lost:

1. an interactive card with buttons
2. a plain one-way card
3. the game's own notification

## One manager, one savegame

A farm folder is bound to one savegame at setup. The mod is installed once and keeps each
savegame's files in its own folder. See
[Run a second savegame](../how-to/second-savegame.md).
