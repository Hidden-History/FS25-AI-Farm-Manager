# Run a second savegame

**One farm folder serves one savegame.** A manager's memory, plans and identity belong to
one farm. It cannot hold two.

The mod is different: you install it once and it keeps each savegame's cards and answers
apart by itself.

## Steps

1. Make a **new, empty folder** for the second farm. Do not copy your first farm folder.
2. Copy the package's `.claude` folder into it, as in [Install](install.md#2-install-the-manager).
3. Start Claude Code **in the new folder** and say "set up my farm manager".
4. When it asks which savegame, pick the second one.

You now have two farm folders:

```
farm-one/     .claude/  sanctum/     → savegame1
farm-two/     .claude/  sanctum/     → savegame2
```

## Using them

Start Claude Code in the folder that matches the savegame you are playing. A session in
`farm-one` only reads and writes for `savegame1`.

## What you will see in game

- A savegame **with** a farm folder shows its own cards and its own figures.
- A savegame **without** one shows a single notice card on the panel the first time you
  load it: "No manager is set up for savegameN". On later loads the panel is empty. Both
  are the correct state, not a fault. (The first-load-only behaviour is read from the mod's
  code and has not been confirmed in game.) The Fields and Productions tabs have nothing
  to show there; the Money and Contracts lines on the Farm tab still do, because they come
  live from the game.

The notice mentions "the skill README". The steps on this page are the current ones.

## Do not

- Do not point two farm folders at the same savegame.
- Do not copy a `sanctum` folder from one farm to another. It holds the first farm's
  history and would be wrong for the second.
