---
class: register
load: C
owns: "this farm's live watchlist of unowned parcels of interest + player-reported prices"
cap_lines: 60
cap_kb: 6
rotation_trigger: on-resolve
archive_target: "history/archive/field-price-watchlist-archive.md"
reconciliation: "resolved parcels (bought or passed) MOVE to archive with price + date, never deleted"
format_version: 1
parity_spec:
  required_sections: ["## Parcels being watched"]
---

# Field Purchase Watchlist

_Unowned fields we're interested in buying, and prices you've reported seeing
in-game. Field ownership itself is not derivable from any save file on its own
(field↔farmland is a spatial relationship resolved via a proprietary raster
layer, not an XML attribute) -- but a field's **purchase price** for an
*unowned* parcel is even less available: it isn't saved anywhere until the
transaction happens, so **this data has to come from the player, every time.**
Don't estimate it from a per-hectare rate unless that rate has actually been
confirmed for this map (a custom map's `farmlands.xml` may set its own
`pricePerHa`, and per-parcel scaling on top of that)._

## Parcels being watched

| Field | Price seen | Date seen | Notes |
|---|---|---|---|
| {{FIELD_ID}} | {{PRICE — as reported by the player, or from farmlands.xml if the per-parcel rate is confirmed for this map}} | {{DATE}} | {{size if known, why it's of interest, anything about its current crop/condition if visible}} |

_Empty is the right state for a farm not currently shopping for land -- say so
rather than leaving the table header with no rows and no comment._

_When a parcel resolves (bought, or decided-against), **move** it -- don't delete -- to
`history/archive/field-price-watchlist-archive.md` with the price and date, so "we priced parcel
86 at $1.06M and passed" survives past the entry's removal from the live list._
