# Set up your farm

Setup happens once per farm folder and takes a few minutes. You need the manager installed
first: see [Install](install.md).

## Steps

1. Open a terminal in your farm folder and start Claude Code.
2. Say:

   > set up my farm manager

   or type `/fs25-farm-manager`.
3. Answer the questions.

## What it asks, in order

1. **Your name, and what language to speak.** These come first. From your answer onward the
   manager speaks that language.
2. **Which savegame.** It finds your savegame folders and you pick one. This farm folder is
   bound to that savegame from then on.
3. **Which farm is yours**, only if the savegame holds more than one farm.
4. **Your game install folder and your mods folder.** It needs them for shop prices and the
   map's own data.
5. **What to call the farm.** It tells you the name your save uses and asks whether to keep
   it.

Then it reads your save and **shows you your real position first**: cash, loan, land, fleet,
the day, the difficulty. Check those numbers. If one is wrong, say so before going on.

Only after that does it ask the things your save cannot answer: your goals, how much risk
you like, your priorities and any house rules.

## What it creates

A `sanctum` folder in your farm folder. This is your farm's memory: plain text files you can
read and edit. Nothing in it is sent anywhere.

```
my-farm/
├── .claude/
└── sanctum/
    ├── config.json     which savegame, your name, your language
    ├── identity/       how this farm's manager thinks and talks
    ├── state/          rosters and per-field notes
    ├── plans/          the plan and each session's plan
    └── history/        session records and the friction log
```

`sanctum` also holds three small files the manager keeps for itself: `watch.pid`,
`watch-marker.json` and `fleet-alert-state.json`. Leave them alone.

A `cache` folder also appears beside `sanctum` once the manager has read your save. It is
safe to delete; the manager rebuilds it.

## It never writes to your savegame

Setup reads your save. It writes only inside your farm folder and inside the mod's own
settings folder. The full list is in [Files on disk](../reference/files-on-disk.md).

## Next

[Daily use](daily-use.md).
