---
name: farm-status
description: Quick FS25 farm status — dispatches the fs25-farm-manager skill's ST menu item. Reads the save, writes nothing.
disable-model-invocation: true
---

Invoke the **`fs25-farm-manager`** skill and dispatch its menu item **`ST` (Status)** for the
farm bound to this project directory.

A quick look at what the save says right now — **not a briefing**. Report the headline facts
plainly and briefly: in-game day and clock, season, weather, cash and loan, owned land,
anything harvest-ready, and any contract that looks time-critical. Numbers, not narrative — no
recommendations, no next actions.

**Write nothing.** No ledger row, no `session_count` increment, no dossier or closeout
updates — those belong to `/farm-briefing` and `/farm-closeout`. A quick look that quietly
performed session-start bookkeeping would put a duplicate row in the finances ledger and
corrupt the very trend the ledger exists to show.

The skill's Ground Rules still apply to what you report: pass `--farm-id`, quote
owned-vs-total where the parser reports both, and if a section carries an `error`,
`calibration_needed: true`, or a failed gate, say so rather than reporting the number as
fact. A `0`, a `null`, and a missing value are three different claims.

$ARGUMENTS
