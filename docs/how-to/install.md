# Install the Farm Manager

The Farm Manager has two halves. You need both for the full experience.

| Half | What it is | Where it goes |
|---|---|---|
| **The manager** | Four Claude Code skills. This is Cyrus: it reads your save and remembers your farm. | A folder of your choice (your "farm folder") |
| **The mod** | `FS25_AIFarmManager25.zip`. It shows cards on screen, carries your answers back, and adds a page to the game menu. | Your FS25 `mods` folder |

The manager works without the mod, but you get no cards and no menu page. The mod alone has
nothing to show.

## Before you start

- Farming Simulator 25 on PC.
- [Claude Code](https://claude.com/claude-code).
- Python 3. No extra Python packages are needed.
- **Windows with WSL** is the tested setup: the game runs on Windows and Claude Code runs in
  WSL. macOS is untested.

## 1. Get the files

Download the package from the
[GitHub repository](https://github.com/Hidden-History/FS25-AI-Farm-Manager) and unpack it.
You should see a `.claude` folder, a `mod` folder and a `docs` folder.

The mod zip on its own is also on
[KingMods](https://www.kingmods.net/en/fs25/mods/79933/ai-farm-manager) and on the
[GitHub releases page](https://github.com/Hidden-History/FS25-AI-Farm-Manager/releases).
Use the mod and the manager from the **same release**. A newer mod with an older manager
shows wrong or missing numbers.

## 2. Install the manager

Make a new, empty folder for this farm. Copy the package's `.claude` folder into it:

```
my-farm/
└── .claude/skills/
    ├── fs25-farm-manager/
    ├── farm-briefing/
    ├── farm-closeout/
    └── farm-status/
```

All four folders are needed. The three small ones are the slash commands.

**One farm folder serves one savegame.** If you play a second savegame, see
[Run a second savegame](second-savegame.md).

## 3. Install the mod

Copy `mod/FS25_AIFarmManager25.zip` into your FS25 mods folder:

```
Documents\My Games\FarmingSimulator2025\mods\
```

Keep exactly one copy of the zip in that folder. Do not unpack it.

Start FS25 and tick **AI Farm Manager 25** in the mod list for your savegame.

## 4. Check it worked

1. Load your savegame and **save it once**. The mod needs a saved game to know which
   savegame it is in.
2. Open the game menu. You should see an **AI Farm Manager 25** page with five tabs.

![The game menu with the AI Farm Manager 25 page selected, showing the five tabs Farm, Fields, Productions, Messages and Settings.](../images/menu-farm-tab.png)

Your page will look like this once your farm is set up. At this point the tabs are mostly empty. That is correct: nothing has been set up yet.

## Next

[Set up your farm](set-up-your-farm.md).

If something does not match, see [Troubleshooting](troubleshooting.md).
