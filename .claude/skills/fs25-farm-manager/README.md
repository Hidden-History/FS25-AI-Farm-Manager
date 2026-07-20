# FS25 Farm Manager — Claude Code Skill

A persistent, friendly farm project manager for **one specific** Farming
Simulator 25 save game. It reads your live save files (deterministically, via
bundled scripts — never by guessing), remembers everything across sessions
in a "sanctum" memory folder inside your own project, and gives you
prioritized recommendations instead of raw data dumps.

## File structure

```
fs25-farm-manager/                  <- put this whole folder in .claude/skills/
├── SKILL.md                        <- the workflow Claude follows (required)
├── scripts/                        <- deterministic parsers + the notification bridge, run as-is, never rewritten
│   ├── xml_utils.py                 shared XML→JSON helper used by every parser
│   ├── locate_save.py               finds FS25 savegame folders on disk
│   ├── init_sanctum.py              bootstraps the sanctum/ memory folder (idempotent)
│   ├── sanctum_maintain.py          check / reconcile / rotate the sanctum's capped files
│   ├── check_sanctum_freshness.py   does the sanctum still match the save? (run at briefing)
│   ├── check_skill_honesty.py       do the skill's docs agree with its own code? (at closeout)
│   ├── check_mods.py                validates a mod zip's structure (modDesc + the icon/source files it promises)
│   ├── farm_snapshot.py             ~4 KB briefing digest — the session-start entry point
│   ├── collect_state.py             full raw snapshot (~12 KB) from every parser
│   ├── notify_farm_manager.py       puts a message on the player's screen — plain, or an
│   │                                actionable card (--id/--action/--choice) (needs the mod)
│   ├── read_replies.py              ingests the player's card replies (replies.xml) into a
│   │                                durable sanctum ledger, deduped by (id, action)
│   ├── wait_for_event.py            the idle-at-zero-cost watcher: run under a persistent
│   │                                Monitor, emits one line when the game writes replies.xml
│   │                                or the savegame (arm at briefing, disarm at closeout)
│   ├── read_environment.py          date / season / time / weather
│   ├── read_economy.py              cash, loan, land ownership (farms.xml + farmland.xml)
│   ├── read_career.py               map, difficulty, timeScale, autoSave, mod list
│   ├── read_game_log.py             parses the engine log.txt into structured events (errors, mod-load failures, shutdown verdict)
│   ├── read_fields.py               crop / growth / ground state per field
│   ├── read_farmland_areas.py       decodes infoLayer_farmlands.grle: per-parcel
│   │                                hectares + cost, and which fields are owned
│   ├── read_game_defs.py            sellable-output vs buyable-input, seed litres/ha, growth states
│   ├── read_fill_prices.py          per-period buy/sell price curve for every fillType (economy.xml)
│   ├── read_storage_capability.py   what a silo accepts — reads fillTypes AND fillTypeCategories
│   ├── read_vehicles.py             equipment condition, fuel, wear
│   ├── read_missions.py             all contracts (offered and accepted)
│   ├── read_placeables.py           silos/storage, animal husbandry, production chains
│   ├── read_prices.py               per-station sell price signals
│   ├── read_sales.py                used-equipment marketplace listings
│   ├── read_equipment_market.py     used listings resolved to their real new price
│   └── read_store_prices.py         store prices from the install + mod zips
├── templates/                       <- copied into the sanctum by init_sanctum.py.
│   │                                   Each carries a prose guide explaining how to
│   │                                   fill it and what not to claim.
│   ├── config.json                  savegame binding (paths, slot, farm name)
│   ├── creed.md                     the manager's identity/tone/standing priorities
│   ├── decision-making.md           this farm's doctrine, written at onboarding
│   ├── session-start-briefing.md    shape of the "start my shift" briefing
│   ├── session-closeout.md          shape of the "close out" report
│   ├── closeout-latest.md           the live "last session" file
│   ├── directives.md                standing long-term plans
│   ├── directive-entry.md           one directive record
│   ├── field-dossier.md             per-field history record
│   ├── husbandry-dossier.md         per-animal-building history record
│   ├── production-dossier.md        per-production-chain history record
│   ├── equipment-roster.md          the fleet
│   ├── equipment-shopping-list.md   wanted iron + looked-up prices
│   ├── field-price-watchlist.md     parcels of interest + their cost
│   ├── finances-ledger.md           cash/loan trend across sessions
│   ├── husbandry-roster.md          animal buildings
│   ├── production-roster.md         production chains
│   ├── field-dossiers/README.md     seeds the per-field dossier folder
│   └── journal/README.md            seeds the session archive folder
└── references/                      <- loaded on demand, each with a stated trigger
    ├── workflow-onboarding.md        first run: bind a save, read it, then interview
    ├── onboarding-steps/             the onboarding workflow's steps (step-01…step-07)
    ├── workflow-briefing.md          menu BR + how to conduct a session
    ├── briefing-steps/              the briefing workflow's steps (step-01…step-08)
    ├── workflow-closeout.md          menu CO
    ├── closeout-steps/              the closeout workflow's steps (step-01…step-07)
    ├── sanctum-upkeep.md             every sanctum file and when it changes. Read at closeout.
    ├── reading-the-save.md           the parsing discipline: absence must never
    │                                 look like data. Read before trusting output.
    ├── decision-making.md            general policy for contracts/storage/animals/selling
    ├── time-mechanics.md             how in-game time actually advances
    ├── crop-calendar.md              general seasonal planting/harvest guidance
    ├── notifications.md              the skill↔mod notification hook — the two-way loop
    │                                 (cards out, replies back) and the event-driven watcher
    └── game-guide/                   FS25HF game reference — grounds facts in the manual
```

`SKILL.md` is the **dispatcher Claude loads**, and deliberately thin: identity, path
conventions, an activation protocol, a **menu**, the never-guess invariants, and the ground
rules that apply to *every* action — `--farm-id`, ownership, and how to tell a real number from
a confident wrong one. The step-by-step workflows live in `references/` as **stepped** files:
each `workflow-*.md` names a `firstStep` and chains through its `*-steps/` folder via each
step's `nextStepFile`, read and followed to the end (no engine enforces the chain).

This README is the **orientation and inventory** — the map of what ships and where. SKILL.md is
what the model actually executes. The two are not interchangeable: dispatch logic belongs in
SKILL.md, inventory prose belongs here, and neither should migrate into the other.

> **`decision-making.md` appears three times, by design** — the blank `templates/decision-making.md`,
> the general-policy guide `references/decision-making.md`, and this farm's filled-in doctrine at
> `sanctum/identity/decision-making.md`. Same name, three roles: template → guide → output.

## The menu, and the slash commands

Once the manager is active it presents a menu — say a code, a number, or just describe what
you want:

| Code | Does |
|---|---|
| `BR` | Briefing — start a session, diff what changed, lead with today's decisions |
| `CO` | Closeout — write the session up, verify the sanctum, hand off cleanly |
| `ST` | Status — a quick look at the save. No ceremony, **writes nothing** |
| `PR` | Prices — what something costs, or what a parcel would cost |

You never have to use the menu. If your first message already says what you want ("give me a
briefing"), it dispatches straight there, and anything that isn't a menu item is just
conversation.

Three optional slash commands are installed alongside the skill for entering cold:
`/farm-briefing`, `/farm-closeout`, `/farm-status`. Each dispatches the matching menu code
rather than restating the workflow — one source of truth. They set
`disable-model-invocation: true`, so they're typeable but stay out of Claude's context and
don't compete with the main skill's triggering.

When you actually use the skill, it will create a **separate** folder in your
own Claude Code project directory — not inside this skill folder:

```
your-project/
└── sanctum/                         <- created automatically on first run
    ├── config.json                  <- this farm's save binding (stays at root)
    ├── identity/                    <- Tier A: identity + doctrine, check-only
    │   ├── creed.md                 <- this farm's manager identity
    │   ├── decision-making.md
    │   └── directives.md
    ├── state/                       <- durable farm facts: registers + dossiers
    │   ├── equipment-roster.md
    │   ├── equipment-shopping-list.md
    │   ├── field-price-watchlist.md
    │   ├── finances-ledger.md
    │   ├── husbandry-roster.md
    │   ├── production-roster.md
    │   ├── field-dossiers/          <- one file per field
    │   ├── husbandry-dossiers/
    │   └── production-dossiers/
    └── history/                     <- append-only + cold archives
        ├── closeout-latest.md
        ├── friction-log.md
        ├── journal/                 <- one archived closeout per session
        └── archive/                 <- all cold shards live here
```

## Installation

1. Choose personal (all your projects) or project-scoped (just this one):
   - **Personal:** copy the whole `fs25-farm-manager/` folder to `~/.claude/skills/fs25-farm-manager/`
   - **Project:** copy it to `<your-project>/.claude/skills/fs25-farm-manager/`

   ```bash
   mkdir -p ~/.claude/skills
   cp -r fs25-farm-manager ~/.claude/skills/
   ```

   Important: `SKILL.md` must sit directly inside `fs25-farm-manager/` — not
   nested another folder deeper — or Claude Code won't find it.

2. Start (or restart) a Claude Code session in your project directory.

3. Say something like *"start my farm session"* or *"give me a briefing on
   my farm."* Claude will notice no `sanctum/` exists yet in your project
   and walk you through onboarding automatically:
   - It runs `locate_save.py` to find your FS25 save folders (this handles
     WSL, where the game runs on Windows and Claude runs in Linux)
   - You confirm which save slot this manager is for — it binds to exactly one
   - It confirms your game install and mods directories, which it needs for
     store prices and the map's own config
   - It reads your save and **shows you the real position first** — cash, loan,
     land, fleet, day, difficulty — before asking you anything that requires
     judgment. This ordering is deliberate: an earlier version asked a planning
     question while a parser bug had it believing the farm was a blank slate,
     and the answer was given on a false premise.
   - It then asks the handful of things the disk genuinely cannot answer —
     your goals, risk appetite, standing priorities, and any house rules —
     and writes `sanctum/config.json`, `sanctum/identity/creed.md`, and
     `sanctum/identity/decision-making.md`

4. From then on, just talk to it naturally each time you play:
   - *"start my shift"* → pulls live save data, gives a prioritized briefing
   - normal conversation → it recommends, you decide, it updates memory
   - *"close out"* / *"that's it for today"* → logs the session, saves
     everything, hands off cleanly for next time

## A few things worth knowing before your first real session

- **Read-only against your game.** The skill never edits your actual save
  XML files — all writing happens inside `sanctum/` in your project.
- **The on-screen loop is two-way, and hands-off.** With the mod installed the
  manager can put an actionable card on your screen — a yes/no, a choice, or a
  free-text reply — and read your answer back: the mod appends your click to
  `replies.xml`, and `read_replies.py` ingests it. You don't poll for it. At
  briefing the manager arms `wait_for_event.py` under a persistent Monitor,
  which idles at ~zero token cost and wakes only when the game writes a reply or
  a save; at closeout it disarms and confirms it's off. See SKILL.md and
  `references/notifications.md` for the wiring.
- **Calibration.** `read_economy.py`, `read_environment.py`, `read_career.py`
  and `read_farmland_areas.py` have been run against a real save and checked
  value-by-value. The rest (`read_vehicles.py`, `read_placeables.py`,
  `read_prices.py`, `read_sales.py`, `read_missions.py`) are structurally
  sound but not independently cross-checked, so they carry a
  `calibration_needed` flag plus a full raw XML dump as a safety net. SKILL.md
  instructs Claude to check that flag and self-correct from the dump. Note the
  flag is necessary but **not sufficient** — it reports whether a tag matched,
  not whether the value is right. Sanity-check the numbers too; that habit
  caught every real bug here, and reading the code harder caught none.
- **Prices and areas are not in your save — but they are not unknowable.**
  New-equipment prices, per-hectare rates, and parcel areas aren't stored
  per-game, but they are all on disk. `read_store_prices.py` reads prices from
  your install and mod zips; `read_farmland_areas.py` decodes the map's
  `infoLayer_farmlands.grle` raster for real per-parcel hectares and cost, and
  resolves which fields you own. It validates that decode against independent
  ground truth already in your save and **refuses to emit numbers** rather than
  guess if those gates fail. The manager should read these rather than ask you.
- **One save per project folder.** If you want the manager for a second
  farm, use a second Claude Code project directory — the skill binds one
  sanctum to one save game on purpose.
