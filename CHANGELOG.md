# Changelog

All notable changes to AI Farm Manager are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
