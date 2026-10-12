# Troubleshooting

Find what you see, then follow the steps.

## The manager cannot find my savegame

Tell it the full path to your savegame folder. In WSL, Windows folders are under `/mnt/c/`,
for example `/mnt/c/Users/<you>/Documents/My Games/FarmingSimulator2025/savegame1`.

## A card was not shown

The manager reports one of three results when it sends a card:

| Result | Meaning |
|---|---|
| 0 | The mod read the card. |
| 2 | Nothing read it. |
| 1 | The manager could not work out where to write. |

A result of 2 means one of these:

1. The game is not running, or no savegame is loaded.
2. The mod is not installed or not ticked for this savegame.
3. The savegame has never been saved. Save once.
4. The farm folder is bound to a different savegame than the one you loaded.

## The menu page shows old numbers

Check the "as of" time on the tab.

1. Is a manager session running? Start one with `/farm-briefing`.
2. Save the game. The manager refreshes its figures on each save.
3. Reopen the page.

If the time still does not move, ask Cyrus "did the last refresh work?". If a refresh
failed it says so, and why.

## "Machines owned" is far too high and "Pallets owned" reads unknown

The mod and the manager are from different versions. Update both: see
[Update](update.md).

## A tab says "... reporting is not available yet"

The manager has not written data for this savegame. Either no farm folder is set up for
it, or no save has happened with a session running. See
[The in-game menu](in-game-menu.md#when-a-tab-is-empty).

## I cannot click a card

Press **Ctrl+Comma** to bring up the mouse cursor. If the key does nothing, look under
Controls for **AIFM: toggle cursor**; another mod may use the same key.

## A card shows as a plain grey box

The panel failed to draw and the mod used the game's own notification. Open the game's
`log.txt` and search for `FarmManager25`. The line says what failed. Please
[report it](../reference/privacy-and-feedback.md).

## I see cards from another savegame

This happened in version 3.0.0.0 and older. Update: see [Update](update.md).

## A field shows an upper-case word instead of a name

That state has no label in this version. It is shown raw on purpose so it is never blank.
Please report the word you see.

## Everything looks wrong after a game update

Ask Cyrus to re-check its readers. The manager's scripts report whether they still trust
what they read, and Cyrus tells you which ones do not.

## Still stuck

Open an issue at
[github.com/Hidden-History/FS25-AI-Farm-Manager/issues](https://github.com/Hidden-History/FS25-AI-Farm-Manager/issues).
Say which version you run (the mod list shows it) and what you see.
