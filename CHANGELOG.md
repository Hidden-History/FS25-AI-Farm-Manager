# Changelog

All notable changes to AI Farm Manager are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
