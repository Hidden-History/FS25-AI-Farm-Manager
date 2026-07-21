# Changelog

All notable changes to AI Farm Manager are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.2.0] - 2026-07-21

### Added

- Setup now asks how you want to play — your scenario, challenge, or preset — so the
  manager's advice fits your run from the start.
- Mouse-wheel scrolling through the on-screen card stack.
- A dedicated keybind (Ctrl+Comma) to raise or lower the mouse cursor. The overlay is now
  usable on foot, not just from inside a vehicle.

### Changed

- The manager now remembers your game settings — such as season length and crop growth mode —
  between sessions, instead of only reading them once during setup.
- Session history now tracks the in-game season and day, so your progress reads on the farm's
  own calendar rather than only the real-world date.
- Shortened the mod's keybind names so they no longer get cut off in FS25's Controls menu.

### Fixed

- When several notifications were active, the on-screen card list could grow to fill most of
  your screen. It's now capped to a fixed number of visible cards, with the rest reachable by
  scrolling.
- Bales stored in modded storage sheds weren't counted in your farm's holdings. They're now
  detected and included in your totals.
- Removed a stretched backdrop panel behind the cards that distorted their rounded corners.
  Cards now render cleanly.

## [2.2.1.0] - 2026-07-20

Initial public release. An AI farm manager for a single Farming Simulator 25 savegame: it
reads your save — read-only, never writing to your game — and remembers your farm across
sessions. With the optional mod installed, it shows notification cards on your screen while
you play and reads your answers back, whether that's a yes/no, a choice, or a typed reply.
Ctrl+Period toggles the overlay between a persistent panel and classic pop-up notifications.
