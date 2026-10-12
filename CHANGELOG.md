# Changelog

All notable changes to AI Farm Manager are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.1.9.0] - 2026-10-12

The first release since 3.0.0.0. Everything below was built and tested as versions 3.1.0.0
to 3.1.9.0; none of those test versions was published, so a player on 3.0.0.0 gets all of
it at once. The version in brackets is the test version a change first appeared in.

### Added

- **A Farm Manager page in the game menu, with five tabs: Farm, Fields, Productions,
  Messages and Settings.** Open the game menu, or press Ctrl+Alt+Period. The Settings tab
  replaces the old settings window. (Farm, Messages and Settings in 3.1.0.0; Fields and
  Productions in 3.1.1.0)
- **The time on every "as of" mark.** Figures the manager wrote from your save now show when
  it read them, on every tab. Figures read from the running game are marked LIVE. (3.1.1.0)
- **A Low fuel count on the Farm tab** that matches the fuel alerts Cyrus sends, because
  both now come from one calculation. When some machines cannot be measured the count
  shows a plus sign, such as "2+", meaning "at least". (3.1.4.0)
- **Machines owned, Pallets owned and Bales owned as three separate lines** on the Farm
  tab. The old "Vehicles owned" figure counted pallets as vehicles. (3.1.5.0)
- **"No contract" in the Fields detail box** for a field the game was checked for and that
  has none. A contract that could not be read still says "unknown". (3.1.6.0)
- **The next crop planned for a field, and your notes on it, in the Fields detail box.**
  The manager keeps a crop plan for each field and shows it there, marked "reviewed" or "not
  yet reviewed with you". A field with no plan says so; a plan or note the manager could not
  read says that, with the reason, and is never shown as "no plan". (3.1.8.0)
- **The manager can say how full each building is.** A new reader, `read_building_capacity.py`,
  matches each storage you own to that building's own definition file and reports its ceiling
  and percent full for silos and production points, and for the storage inside animal barns
  (not the number of animals or the feed capacity: see Known gaps). A building it cannot
  match is named with the reason and no figure. Before, the manager said it could not tell
  whether anything was at capacity. (3.1.8.0)
- **Planting windows and ready / dead dates per field come from a shipped script,**
  `project_crop_calendar.py`, instead of one the manager wrote for itself. Dates are given as
  windows with the assumptions stated, and a crop such as potato that needs you to cut the haulm
  first gets "needs your step" with its window rather than no date. A date it cannot work out is
  "unknown" with the reason. On a save whose crop growth mode is DAILY (or not known) the
  script gives no planting window and no date at all, because the seasonal table is not what
  grows crops there; the manager says so and asks you for timing. (3.1.8.0)
- **The Productions tab shows each building's own capacity.** It used to refuse ("capacity
  refused") whenever two buildings sharing a recipe had different tanks. It now reads each
  building's own definition file. A building with no definition file to read (a pre-placed map
  object) keeps its refusal, with the reason. (3.1.8.0)
- **The crop plan is a standing duty.** The manager builds a next crop and plant window for
  every field at onboarding, keeps them current, shows you what is unapproved and asks you to
  approve it, and tells you about any field it could not plan. You can tell it to stop asking. (3.1.8.0)

### Changed

- **The in-game mod description is correct again.** It now says that replies and the message
  bridge are kept per savegame, that the settings are a tab in the game menu, and it no longer
  claims the camera stays still while the mouse cursor is up. (3.1.7.0)
- **The download now includes the player documentation, this changelog and the licence files,**
  and no longer includes the developer test cases. (3.1.7.0)

- **Crops and ground states are shown in words.** A crop uses the game's own name for it
  ("Oat"), bare ground reads "No crop", and ground states read "Ploughed", "Sown",
  "Seedbed", "Rolled seedbed", "Cut grass", "Ridged" and so on, in place of upper-case
  codes. A state this version has no label for is still shown as its code, so the line is
  never blank. (3.1.5.0, more states in 3.1.6.0)
- **A figure the manager refused to give now says why.** Storage fill, Points at capacity
  and Low fuel read "capacity refused" when the capacity they need could not be worked
  out. Other unread lines keep the plain "unknown". (3.1.5.0)
- **The Productions detail's first column is headed "Fill type".** It was headed "Input"
  even above output rows. (3.1.2.0)
- **In German, Spanish, French and Polish, most of the Farm Manager page is still in
  English.** Tab names, column headings, setting names and help text are English copies in
  those four files. Only a small group of labels (the day groups, the footers and a few
  others) is translated.
- **The manager's notes and messages no longer refer to our internal tracker.** Wording only;
  nothing the manager does has changed. Notes already saved in an existing farm folder keep
  their old wording, and the manager does not rewrite them.

### Fixed

- **Every savegame showed the same cards.** The mod kept one card store for the whole
  install, so loading a different save showed you the previous one's cards — and re-saved
  them, in every save, forever. Cards, on-screen messages and your in-game replies are now
  stored per savegame, so each save shows only its own. (3.1.0.0)

  Cards you had not yet dismissed are cleared once, on upgrade. They could not be attributed
  to a savegame, and guessing would have been worse than starting clean. Your panel position
  and settings are kept.

- **Replies could be credited to the wrong farm.** Answers you gave in-game were written to a
  single shared file; if the manager had not yet read them, the next farm's session claimed
  them as its own answers. Replies are now per savegame, and any un-read replies left in the
  old shared file are discarded on upgrade rather than credited to whichever farm loads first
  (their ids are written to the game log).

- A savegame you have not set up a manager for now says so on the panel instead of sitting
  blank. One manager install serves one savegame, in its own directory — an empty panel there
  is the correct state, not a fault.

- **The contract figures on the Fields and Farm tabs were never filled in.** The read
  failed on every farm. It now works, and it skips missions that are not tied to a field.
  (3.1.1.0)
- **The page had no background, and several labels sat in the wrong place.** The page
  background is drawn, and stand-alone text is anchored where the design puts it. (3.1.1.0)
- **Separator lines did not draw, list rows ignored their set height, and the filter
  buttons and status chips were unpadded.** (3.1.2.0)
- **Cyrus told every farm it owned no sprayer.** What you own is now reported as "owned",
  "not found among the N machines that could be read", or "unknown". It never reports
  something as missing when it only failed to look. (3.1.3.0)
- **Shortened lists hid entries Cyrus needed.** Every shortened list can now be read in
  full, and the owned-field crop groups add up to the number of fields you own. (3.1.3.0)
- **The Fields tab could stay old after a refresh that said it had worked.** The refresh
  line now says what was and was not rewritten. (3.1.3.0)
- **A field merged from several parcels raised a false "land sold" note.** Cyrus now asks
  about merged fields and records the merge. (3.1.3.0)
- **The Farm tab and Cyrus's fuel alerts disagreed.** (3.1.4.0)
- **A round baler saved with a finished bale inside stopped the Farm tab updating.**
  (3.1.5.0)
- **A machine with an empty fuel tank was missing from the Low fuel count** and raised no
  fuel alert. (3.1.5.0)
- **An emptied water or liquid tanker was reported as out of diesel.** Only a machine with
  an engine can be low on fuel. (3.1.5.0)
- **A tanker carrying diesel as cargo was reported as a nearly empty fuel tank** when its
  load was at 25 % or less. (3.1.6.0)
- **Figures from the author's own farm appeared in shipped text.** Removed. (3.1.5.0)
- **Fuel and repair alerts are on for every farm.** The alert check reads its own on/off switch
  (`fleet_alerts_enabled` in `config.json`); a farm with no such key counts as on. The
  manager had skipped the check because the instructions pointed at a setting a fresh install
  did not have. (3.1.8.0)
- **Weeds at level 5 were sent to a weeder.** The game's own weed table gives a weeder and a
  hoe no action at level 5, moves herbicide's target to level 9, and sends only a mulcher to
  zero (which destroys a standing crop). The manager's reference now carries the table, tells it
  to offer the tools the field's own check lists, and says plainly that whether a sprayed level
  still costs yield is not known. The field check's `tools_that_change_without_clearing` is
  renamed `tools_that_move_it_to_another_state`. (3.1.8.0)
- **Lime level 0 was reported as "unknown".** The reference now says what the levels mean and
  when a field needs lime, from the game's own data. (3.1.8.0)
- **Rates and days of cover built from two saves came with no warning.** Any such figure now
  states the window it was measured over and that a delivery or refill inside it would change
  it, and is withheld when the window cannot support it. (3.1.8.0)
- **Accepting a field contract could break it until you reloaded the save.** The Farm tab read
  every offered contract's completion, and on a contract you had not accepted that read left the
  game's own progress tracking half set up. Once you accepted the contract the game then failed
  on every frame and the contract never tracked. The manager now reads completion only from
  contracts that are running. With no running contract the Contracts completion figure shows
  as unknown instead of an average that included offered contracts. (3.1.9.0)

### Known gaps

- Some layout differences from the design remain on the Farm and Messages tabs.
- **A crop plan you approve, or a field note the manager records, reaches the Fields tab only
  after the next game save,** or after a refresh run by hand (`refresh_state.py now`). When you
  approve a plan, the manager prints that the next refresh publishes it; that is true, but the
  next refresh comes with your next save.
- **The manager's save watcher can lapse during a long session.** A save that lands while it is
  not running leaves the figures old, and the manager refuses to read them until the watcher is
  started again and a refresh is run.
- **Two mods that define a production with the same name can confuse the Productions
  figures.** The manager can take inputs from the other mod's recipe, so a line can show an
  input (propane, for example) its building does not use, and many runways read "unknown".
- **One unreadable mod file, such as a zero-byte mod zip, makes the production inputs
  unavailable, and the manager does not name the file.** In the one case seen, replacing the
  broken zip with a good copy cleared it.
- **On a farm with merged fields, the crop-state counts in a briefing can count the absorbed
  parcels as separate fields,** so "harvest ready" can read too high. The merged field's own
  row is the right one.
- **The manager cannot report how many animals a barn holds or its feed capacity from its
  scripts.** It reads the building's file by hand when asked. Purchase prices for animals are
  not readable at all, so it asks you for them.

## [3.0.0.0] - 2026-08-17

A new architecture for how Cyrus reads your farm, plus a round of fixes from the manager's
first live sessions on a real save.

### Added

- **Setup now asks your name and what language to speak, right at the start.** Before this,
  the manager never asked either — it addressed you as "partner" and spoke English no matter
  what language you actually use. Now it asks first, and speaks the language you give it from
  that point on.
- **A new cache layer.** Dedicated scripts now gather your farm's state and write it to a
  verified cache whenever the game saves — including pushing fleet fuel/repair alerts
  straight to your on-screen overlay the moment a threshold is crossed, with no need to ask.
  Cyrus reads what those scripts already produced instead of gathering and reporting
  everything itself in one conversation, so a session starts from more of what the game
  knows, read the same way every time.
- **Closeout can now offer to send issues to the project's GitHub tracker.** At the end of a
  session, if anything logged looks like a product defect, Cyrus asks whether to send it —
  and always asks whether there's anything else you'd like added or changed, defect or not.
  Every issue is scanned and the scan result is told to you plainly ("scanned for usernames,
  home paths and author identifiers" — not a claim your finances were checked); you see the
  exact title and body before anything is sent, and approve, edit, defer, or drop each one
  individually. Nothing is batched, and nothing goes anywhere without your say-so.
- Setup now asks which farm is yours when your save has more than one (for example, a joined
  multiplayer save), instead of assuming.
- **A field-by-field work list of what needs doing today.** Each field reports the operation
  its own state calls for — ploughing, liming, weeding, and more — grounded in the same read
  of the field's own state, not a generic checklist, and with the reading behind each
  recommendation carried alongside it.
- **Cyrus can now tell you which of your production lines are running dry**, and how many
  hours you have before each one empties — checked against that line's own input stock, not
  your farm's stock as a whole, so a full silo elsewhere doesn't hide a bin that's actually
  about to run out. Where the underlying data can't say, it tells you that instead of
  guessing.

### Changed

- The "can I sell this?" check no longer states a flat "no" it can't actually back up. It
  previously could tell you an item you own (manure, wool, milk, and others) can't be sold,
  when it had simply not found where — it now only reports what it has confirmed.
- File-size limits on your farm's memory files are now recommendations that warn when
  crossed, instead of hard caps that block you from continuing. Your farm can also record its
  own preferred size, which overrides the shipped recommendation.
- A mistyped notification command is no longer reported as "the game must be closed" —
  argument mistakes and real delivery failures are now told apart.

### Fixed

- Several documented commands referenced a Claude Code variable not defined in current
  versions, so they silently could not run. Every command in the skill now uses a direct
  path.
- Updating an older farm's memory to a newer format now always backs up your data first, or
  refuses to run — it could previously destroy your only restore point if interrupted
  partway through.
- A background freshness check could keep reporting your farm's cached data as out of date
  immediately after it had just been refreshed. Fixed for the affected data sources.
- "I have no mods" is now accepted as a complete, final answer during setup — the manager no
  longer keeps re-asking or goes searching your disk for a folder that isn't there.
- Checking what equipment you're missing could time out on a large fleet; it now gets more
  time to finish that specific check.
- A quick freshness check on your cached data (used when a full re-check would take too long)
  could report that data as "verified" when it had only compared each file's timestamp and
  size, never read its actual contents. It no longer claims more than it checked.
- Every field's crop-growth stage was reading as unknown, always, on every save — a step in
  building the underlying growth-stage table was silently missing its data, so the table
  never built. It now builds correctly, and crop state populates the way it was always meant
  to.
- Whether a crop was ready to harvest was being judged by the *name* of its growth stage
  instead of the flag that actually marks it ready. On this map several crops have a stage
  named as if it were ready when it isn't, while the truly ready stage is named something
  unrelated — so a crop could read as ready when it wasn't, and vice versa. Readiness is now
  read from the correct flag.

## [2.2.3.0] - 2026-07-23

### Added

- Setup now asks how you want to play — your scenario, challenge, or preset — so the
  manager's advice fits your run from the start.
- Mouse-wheel scrolling through the on-screen card stack.
- A draggable scrollbar on the card panel, so you can scroll through your notifications even
  without a mouse wheel.
- A dedicated keybind (Ctrl+Comma) to raise or lower the mouse cursor on foot, so you can
  click, drag, and scroll the notification panel without needing to be in a vehicle.
- A settings page (Ctrl+Alt+Period, on foot or in a vehicle): toggle the panel on/off, change
  its size, reset its position, and set how long messages linger when the panel is off.
- The manager now keeps a single running plan for your farm — read at the start of every
  session and updated as decisions are made — instead of only tracking scattered long-term
  notes. Nothing to set up; it starts empty and fills in as you play.

### Changed

- The manager now remembers your game settings — such as season length and crop growth mode —
  between sessions, instead of only reading them once during setup.
- Session history now tracks the in-game season and day, so your progress reads on the farm's
  own calendar rather than only the real-world date.
- Shortened the mod's keybind names so they no longer get cut off in FS25's Controls menu.
- The notification overlay now renders at higher resolution, so the cards, panel, and top bar
  stay crisp on high-resolution (1440p/4K) displays instead of looking soft, and the scrollbar
  sits clear of the cards.

### Fixed

- When several notifications were active, the on-screen card list could grow to fill most of
  your screen. It's now capped to a fixed number of visible cards, with the rest reachable by
  scrolling.
- Bales stored in modded storage sheds weren't counted in your farm's holdings. They're now
  detected and included in your totals.
- Removed a stretched backdrop panel behind the cards that distorted their rounded corners.
  Cards now render cleanly.
- Long notification titles no longer run past the edge of the card or overlap the timestamp —
  they're shortened with an ellipsis when needed.

## [2.2.1.0] - 2026-07-20

Initial public release. An AI farm manager for a single Farming Simulator 25 savegame: it
reads your save — read-only, never writing to your game — and remembers your farm across
sessions. With the optional mod installed, it shows notification cards on your screen while
you play and reads your answers back, whether that's a yes/no, a choice, or a typed reply.
Ctrl+Period toggles the overlay between a persistent panel and classic pop-up notifications.
