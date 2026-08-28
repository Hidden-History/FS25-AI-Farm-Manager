---
class: register
load: C
owns: "this farm's live buy/sell decision log for equipment — considered trades, not a wish list"
cap_lines: 80
cap_kb: 8
rotation_trigger: on-resolve
archive_target: "history/archive/equipment-shopping-list-archive.md"
resolved_markers: ["BOUGHT", "SOLD", "DISMISSED"]
reconciliation: "resolved entries (bought/sold/dismissed) MOVE to archive with date + resolution, never deleted"
format_version: 2
parity_spec:
  required_sections: ["## Watching to buy", "## Watching to sell"]
---

# Equipment Watchlist

_Things we've decided are worth buying (new or used) when the price/timing is
right, and things we've decided to sell. This is a decision log, not a wish
list -- an entry means the farm has actually thought about the trade, not just
noticed a machine exists._

**New-equipment prices for anything not yet owned are usually readable, not
guessable.** Run `read_store_prices.py` before asking the player what something costs — it
resolves store prices from the install and mod zips directly (`--search`/`--lookup`/`--gaps`),
so there is no need to hand-locate a price XML under `config.json`'s `paths.install_dir`/
`paths.mods_dir` yourself. **Used-market listing prices are readable too** — run
`read_equipment_market.py`: every listing carries its `listed_price` straight off `sales.xml`,
and where the listing resolves to a matching new-price item it also computes `discount_vs_new`/
`discount_pct` — the actual "is this a bargain?" number. Only the item's `new_price` can be
genuinely unresolved (no store match); when that happens the listing still carries its
`listed_price`, just without a discount comparison to weigh it against.

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
