---
class: ledger
load: B
owns: "this farm's cross-session cash/loan trend — one opening-snapshot row per session"
cap_lines: 180
cap_kb: 15
rotation_trigger: segment-and-retain
archive_target: "history/archive/finances-ledger-archive-{first}-{last}.md"
reconciliation: "one row/session opening snapshot, never a 2nd row; rotate oldest whole rows verbatim, row-count conservation-checked, never summarized"
format_version: 1
parity_spec:
  required_sections: ["## Standard columns (every farm)", "## If this farm runs a house-rule ledger", "## What \"trending well\" means", "## Rotation — segment-and-retain"]
---

# Finances Ledger

_One row per session, appended at **session start** as that session's **opening**
snapshot (so a session that ends abruptly still left evidence). Used to see whether
cash and loan are trending somewhere good or bad across sessions -- a single briefing
can't show a trend, only this can._

**Closeout completes that row's Notes; it never appends a second row.** Every row is
an opening figure, so the column stays comparable and the trend is measured
open-to-open. A second row at closeout would silently mix opening and closing figures
in the same column -- and a trend line built from a column that means two different
things on different rows is worse than no trend line, because it still looks like one.
A session's *achievement* is the delta to the next row, plus the closeout narrative in
`history/journal/` -- not another row here. (SKILL.md's Closeout section states the same rule;
if these two ever disagree, that's a bug in one of them, not a choice.)

**Every column must say where its number comes from.** The rule that matters more
than any specific column: **a ledger must make it impossible to confuse a derived
or house-rule number with the game's own save data.** If this farm ever tracks
something other than the save's raw cash/loan (a repayment plan, a stricter
self-imposed budget, anything from `config.json`'s `notional_budget` block), that
tracked figure gets its **own column**, clearly labeled, sitting *next to* the
real save figures -- never in place of them. A reader should never have to guess
which column is "what the game says" and which is "what we've decided to track
instead."

## Standard columns (every farm)

| Session | In-game day | Cash | Loan | Notes |
|---|---|---|---|---|
| 0 (anchor) | {{DAY}} | {{CASH — from farms.xml `money`}} | {{LOAN — from farms.xml `loan`}} | Opening snapshot at onboarding. |

## If this farm runs a house-rule ledger

Only add these columns if `config.json`'s `notional_budget.enabled` is `true`, and
only after that block's formula is actually filled in. Label the extra columns for
exactly what they are, and restate the formula/source at the top of the file (don't
make a reader hunt in `config.json` for it):

| Session | In-game day | Cash (real, save) | Loan (real, save) | Cash (tracked) | Debt outstanding | Notes |
|---|---|---|---|---|---|---|
| 0 (anchor) | {{DAY}} | {{REAL_CASH}} | {{REAL_LOAN}} | {{TRACKED_CASH — state the formula once here, e.g. "real cash − offset"}} | {{DEBT — and state here whether it's frozen, amortizing, or something else}} | {{e.g. opening balance sheet, what set the anchor}} |

If real cash or loan ever moves in a way the tracked formula doesn't explain (a
top-up, an untracked sale), **say so in the Notes column rather than quietly
re-anchoring the formula** -- silently absorbing the discrepancy is exactly the
kind of thing this ledger exists to catch.

## What "trending well" means

Don't just report the latest row -- glance back a few sessions at briefing time.
Cash climbing while a loan/debt figure holds flat isn't progress, it's a bigger
pile of cash sitting next to the same obligation. If this farm tracks a debt or
loan figure at all, that figure trending down is the number that actually matters;
say so if a briefing's trend line disagrees with what the raw cash number implies.

## Rotation — segment-and-retain

This is a true chronology, so it's **segment-and-retain**, not summarize-and-drop — every archived
row must stay individually inspectable (a specific session's exact cash/loan may matter later, e.g.
to check whether a house-rule formula held).

- **Trigger:** row count > 25.
- **Mechanism:** move the **oldest 15 rows verbatim** (never summarized) into
  `history/archive/finances-ledger-archive-{{first}}-{{last}}.md` (named by the session range it
  holds), leaving the live table with the most recent ~10 rows plus a one-line pointer
  (`Earlier sessions: see finances-ledger-archive-{{first}}-{{last}}.md`).
- **Archive index header:** each archive shard opens with a running index — first/last session,
  min/max cash, min/max loan — so "how has this farm trended since the beginning" doesn't require
  reading every shard in full.
- **Conservation check:** before deleting the moved rows from the live file, verify
  `archive row count + live remaining row count == pre-rotation total`. Never summarize old rows
  into an "average trend" line — the whole point is the per-session figures.
