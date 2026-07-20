---
class: register
load: C
owns: "this farm's live buy/sell decision log for equipment — considered trades, not a wish list"
cap_lines: 80
cap_kb: 8
rotation_trigger: on-resolve
archive_target: "history/archive/equipment-shopping-list-archive.md"
reconciliation: "resolved entries (bought/sold/dismissed) MOVE to archive with date + resolution, never deleted"
format_version: 1
parity_spec:
  required_sections: ["## Watching to buy", "## Watching to sell"]
---

# Equipment Watchlist

_Things we've decided are worth buying (new or used) when the price/timing is
right, and things we've decided to sell. This is a decision log, not a wish
list -- an entry means the farm has actually thought about the trade, not just
noticed a machine exists._

**New-equipment prices for anything not yet owned are usually readable, not
guessable.** Check `config.json`'s `paths.install_dir` (base game) and
`paths.mods_dir` (modded equipment) for the store's own price XML before asking
the player what something costs -- see `state/equipment-roster.md` for the same
caveat. **Used-market prices are genuinely not in any file** -- those have to
come from what the player reports seeing in-game.

## Watching to buy

| Item | Price | Source | Date noted | Why |
|---|---|---|---|---|
| {{MACHINE}} | {{PRICE}} | {{store XML (state the file) \| player-reported in-game listing}} | {{DATE}} | {{what gap this fills, and what it costs against current cash/budget}} |

## Watching to sell

| Item | Est. resale | Source | Date noted | Why |
|---|---|---|---|---|
| {{MACHINE}} | {{ESTIMATE — note if this is a guess; resale value isn't reliably in any file either}} | {{basis for the estimate}} | {{DATE}} | {{why it's a sell candidate -- idle, redundant, raising cash for something else}} |

_Empty sections are a legitimate state -- a farm with nothing currently worth
buying or selling should say so plainly rather than leaving stale entries in
either list._

_When an entry resolves (bought, sold, or dismissed), **move** it -- don't delete -- to
`history/archive/equipment-shopping-list-archive.md` with its resolution and date, one line each.
That preserves "we already considered and rejected X" so it isn't re-proposed and re-litigated
identically next session. The archive is tiny per entry; no cap at realistic farm scale._
