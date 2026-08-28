---
class: register
load: B
owns: "this farm's single living plan — the current-focus narrative plus the standing directives (open, paused, recently-closed) it is built from"
cap_lines: 200
cap_kb: 14
rotation_trigger: age-or-cap
archive_target: "history/archive/plan-{YYYY}.md"
reconciliation: "the Current focus narrative is rewritten in place each session (never appended-to); active/paused directives are the live slice, closed ones relocate whole (never deleted) with a dated pointer"
format_version: 1
parity_spec:
  required_sections: ["## Current focus", "## Standing directives", "## How entries accumulate", "## Closing a directive honestly", "## Rotation — moving closed entries to cold storage"]
---

# The Farm Plan

## Current focus

Autumn wheat is in and the header is serviced. The near-term work is storage, not fieldwork:
the west silo is full to within a few hundred litres and the next canola cut has nowhere to
go. Two of the standing directives below are waiting on that same decision, so resolving
storage unblocks more than it looks like from the field list.

Cash is comfortable but not idle-comfortable — the loan payment lands before the canola sale
clears, so the order of operations matters more than the totals do this month.

- Finish the west-boundary drainage before the ground turns.
- Decide storage: extend the west silo, or contract-sell canola straight off the field.
- Review the two paused directives once the storage call is made — both assume the silo.
- Keep the header serviced on the 50-hour interval; it is the only one on the farm.

## Standing directives

_One entry per long-term item. Every entry carries the same fields, none optional: **Status**,
**Set on**, **Goal**, **Plan**, **Review when**, **Last touched**. `unknown` is a real answer;
a skipped field is not._

### Settle the canola storage question before the next cut

- **Status:** active
- **Set on:** session 1
- **Goal:** Have somewhere to put the autumn canola that is not "sell it immediately at
  whatever the co-op is paying that day."
- **Plan:** Price the west silo extension against three cuts' worth of contract sales. Do not
  commit until the extension quote and the standing contract rate are both in hand — the whole
  point of this directive is to stop the farm defaulting to a panic sale.
- **Review when:** before the next canola cut, or immediately if the co-op rate moves more
  than 10%.
- **Last touched:** session 5.

### Finish the west-boundary drainage

- **Status:** active
- **Set on:** session 2
- **Goal:** Stop the west boundary of field 3 waterlogging every autumn; it has cost part of
  a cut two years running.
- **Plan:** Trench the low corner first — that is where the standing water actually sits —
  then reassess before committing to the full boundary run. Doing the whole boundary up front
  was rejected once already: the cost was not justified by evidence that the rest of the line
  floods at all.
- **Review when:** after the first heavy rain following the trench work.
- **Last touched:** session 5.

### Decide whether a second tractor is justified

- **Status:** paused
- **Set on:** session 2
- **Goal:** Know whether the farm is actually bottlenecked on tractor hours or on operator
  hours, and buy only if it is the former.
- **Plan:** Log the hours the existing tractor is genuinely unavailable across a full autumn
  before pricing anything. Paused deliberately: the storage decision may change the workload
  shape enough to invalidate whatever the log says.
- **Review when:** once the storage directive closes.
- **Last touched:** session 4.

### Work out whether the east fields are worth keeping in rotation

- **Status:** paused
- **Set on:** session 3
- **Goal:** Decide whether fields 9 and 11 earn their inputs, or whether they should go to
  grass.
- **Plan:** Needs two more harvests of per-field yield before there is anything honest to
  compare. Paused rather than active because there is genuinely nothing to do on it yet —
  marking it active would imply work is in flight that is not.
- **Review when:** after the next two harvests on 9 and 11.
- **Last touched:** session 3.

### Get the standing crop-rotation plan written down

- **Status:** active
- **Set on:** session 4
- **Goal:** A rotation the player can follow without re-deriving it every spring.
- **Plan:** Draft from the last three seasons of what was actually planted where, not from a
  textbook rotation — the point is a plan this farm will follow, not an ideal one it will
  quietly abandon in the first wet spring.
- **Review when:** before spring seeding.
- **Last touched:** session 5.

### ~~Confirm the header is serviceable before the autumn wheat cut~~ — CLOSED

- **Status:** ✅ done, session 4.
- **Outcome:** Serviced and cut without incident.
- **What actually happened:** Opened as blocking on the assumption the 50-hour service was
  overdue. It was not — the hour meter had been misread against the wrong interval. The
  machine was inside its window the whole time, and the service that was eventually done was
  routine, not remedial.
- **Lesson:** Read the interval off the machine before calling a service overdue. This is the
  second time a "blocking" item on this farm turned out to be a misread number rather than a
  real constraint.

### ~~Establish whether the north field boundary is actually the farm's~~ — CLOSED

- **Status:** ✅ done, session 3.
- **Outcome:** It is not. The strip north of field 6 belongs to the neighbouring farm.
- **What actually happened:** The strip had been worked as if it were part of field 6 because
  the field dossier listed a hectare figure that included it. The savegame's farmland
  ownership data says otherwise, and the dossier was corrected. No money was lost, but two
  sessions of planning had assumed roughly four hectares the farm does not own.
- **Lesson:** A hectare figure in a dossier is not ownership evidence. Ownership comes from
  the farmland data and nowhere else — this is precisely the class of mistake the friction log
  exists to stop repeating.

### ~~Price a grain dryer~~ — CLOSED

- **Status:** ✅ done, session 3.
- **Outcome:** Not viable at this farm's throughput. Shelved, not rejected on principle.
- **What actually happened:** Priced against the moisture penalties actually paid over two
  autumns. The penalties did not come close to the purchase, and the payback horizon ran past
  the point where the numbers mean anything.
- **Lesson:** Price a machine against penalties actually paid, not against the worst season
  anyone can remember.

### ~~Decide whether to take the long-haul milk contract~~ — CLOSED

- **Status:** 🚫 abandoned, session 2.
- **Outcome:** Abandoned. The farm has no dairy and no plan to start one.
- **What actually happened:** The directive was opened from a contract board listing without
  checking whether the farm could service it at all. It could not, and never could have.
- **Lesson:** Check capability before opening a directive on an opportunity. An entry that was
  never actionable still costs every future briefing the time it takes to read and skip it.

### ~~Investigate the fuel-usage spike in session 2~~ — CLOSED

- **Status:** ✅ done, session 3.
- **Outcome:** Explained. Not a fault.
- **What actually happened:** The spike traced to the drainage work — hours on heavy ground
  with the loader, not a leak or a failing machine. The usage figure was real; the alarming
  reading of it was not.
- **Lesson:** An unusual number is a question, not a finding. Say "this is unexplained" and go
  look, rather than reaching for the most alarming explanation that fits.

### ~~Settle whether the co-op or the mill pays better for wheat~~ — CLOSED

- **Status:** ✅ done, session 4.
- **Outcome:** The mill, but only above roughly a full trailer load; below that the haul eats
  the difference.
- **What actually happened:** The first comparison ignored haulage entirely and concluded the
  mill won outright. Redone with haulage included, the answer became conditional on load size.
- **Lesson:** A price comparison that ignores the cost of getting there is not a comparison.

### ~~Check whether the south paddock needs reseeding~~ — CLOSED

- **Status:** ✅ done, session 2.
- **Outcome:** No reseed needed this year.
- **What actually happened:** Assessed directly rather than from the previous season's note,
  which had described it as thin. It had recovered.
- **Lesson:** A note describing a field's condition expires. Re-look before acting on it.

### ~~Decide whether the aging round baler is worth another season~~ — CLOSED

- **Status:** ✅ done, session 4.
- **Outcome:** Kept for one more season rather than replaced.
- **What actually happened:** A replacement looked justified on age alone — the baler is the
  oldest implement on the farm. Priced a new round baler against the repair history of the
  current one, then against the downtime it actually caused. The repairs over the last two
  autumns came to a small fraction of a new machine, and the baler cleared both seasons of
  straw without a breakdown that held up a cut. The age was real; the failure rate implied by
  it was not.
- **Lesson:** Age is not a failure rate. Price a replacement against the downtime and repair
  cost actually incurred, not against how old the machine feels or how much worse a breakdown
  mid-harvest would be than the breakdowns that have actually happened.

## How entries accumulate

Append a new directive entry whenever a plan, goal, or open question is meant to outlive this
session — not for anything that resolves before closeout. Newest or most-active first is the
ordering used here. Each briefing checks this file and says something if an entry is due for
review; that is the whole point of writing it down instead of leaving it in the conversation
that created it.

## Closing a directive honestly

When a directive resolves, do not delete it — strike the title and mark it closed, then write
what **actually** happened, even if that contradicts what the directive assumed when it was
opened. A directive that turns out to have been wrong about its own premise is exactly the
kind of thing worth keeping a record of; closing it quietly erases the lesson along with the
open item.

A directive that simply succeeds as planned deserves the same honesty in **Outcome** and
**What actually happened** — "worked as planned" is a fine answer when true, but say so
explicitly rather than leaving the reader to infer it from the status flipping to done. When a
directive closes, fold whatever it changed into **Current focus** above, so the narrative and
the register never disagree.

## Rotation — moving closed entries to cold storage

This file is loaded at every briefing, so it cannot grow without bound. Closed directives are
relocated to cold storage, never deleted — nothing is lost, only moved. The Current focus
narrative is not rotated; it is kept bounded by being rewritten in place, not by archival.

- **Trigger (`age-or-cap`):** on session close, if this file is over `cap_lines`/`cap_kb`,
  **or** a `done`/`abandoned` directive has been closed for more than one full in-game season
  with no further touch — whichever comes first.
- **What never rotates:** `active` and `paused` directives, and the Current focus section — a
  live plan is never swept away mid-review. Only `done`/`abandoned` directives are
  rotation-eligible.
- **Mechanism:** move the closed directive's full text, unedited (its Outcome / What actually
  happened / Lesson fields are exactly what is worth keeping), to
  `history/archive/plan-2026.md`, and replace it here with one dated pointer line:
  `- _[archived DATE] "TITLE" (N lines) → history/archive/plan-2026.md_`.
- **Conservation:** the archive file is append-only and kept in full; only the always-loaded
  live file sheds bulk. Prove nothing is lost before writing (the archive-not-delete
  discipline). `cap_lines`/`cap_kb` is a recommendation, not a limit — `sanctum_maintain.py
  rotate` reports `compound` with a `warning` rather than moving these entries itself, because
  they are prose blocks rather than table rows — the move is the agent's job, and it is normal
  upkeep, not a failure.
