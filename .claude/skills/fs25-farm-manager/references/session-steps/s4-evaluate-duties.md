---
name: s4-evaluate-duties
description: 'Apply every admissible duty''s rule to the state view and emit its structured output. This is PLAN — iterate the duty register as data, never as a list of steps.'
nextStepFile: './s5-escalate-deliver.md'
---

# S4: Evaluate the duty register

**Progress: Step 4 of 5** — Next: Escalate and deliver

**This is PLAN.** S2 delivered a state view you rated trustworthy; this step turns it into
findings. Read `references/duty-register.md` — it holds the 16 duties as **data**, and this step
is the loop that walks them.

## ⛔ Iterate the register. Do not re-implement it here

**The register is the authority; this file is only the loop.** Walk its rows in order, D-01
through D-16, and for each one apply its own rule to the state view and emit its own
`output_schema`.

**Adding a duty adds a ROW to the register — never a step, never a file, never a branch here.**
That is the whole point of holding the duties as data: a seventeenth duty must be one edit to one
file, and if satisfying it ever requires editing *this* step, the register has stopped being data
and the design has regressed. Likewise, **do not hard-code a duty's fields into this loop** — read
them from its row, so a corrected `empty_means` takes effect without touching the workflow.

If this file and the register ever disagree, **the register wins**; and if the register and the
Duty Map ever disagree, re-derive from the Duty Map.

## Every row emits `status`, and every row says what empty means

Two fields are non-negotiable on every duty's output:

- **`status`** — always present. A duty that could not be evaluated says so; it does not omit
  itself from the results. **An absent duty reads as a duty with nothing to report**, and those
  are different answers.
- **`empty_means`** — what an empty or zero result actually *means* for this duty, taken from its
  row. **Never emit a bare empty list or a bare zero.** "No fields ready to harvest" and
  "readiness could not be determined" are both empty lists and must never render the same way;
  "confirmed empty" and "unreadable" are both zero and must never render the same way. Each row
  already states its own distinction — carry it, do not re-invent it.

This is the project's top defect class, so it is worth stating plainly: **a clean, plausible,
incomplete answer with no caveat is worse than an error.**

## The three degradation axes, per row

Each row carries its own degradation behaviour. Apply the row's, not a general instinct:

- **Axis 1 — the farm genuinely has none of what this duty needs.** Take it from the row's
  `degradation.axis1`. Usually `status: unknown_by_design` with `empty_means` naming the reason
  ("you own no livestock", "you own no production points"). **This is a real answer, not a
  failure** — and several duties are explicitly *unchanged* on this axis because every farm has
  cash, land, machines and weather.
- **Axis 2 — the reader that feeds this duty could not run at all.** This one is **uniform across
  every row**: `status: unavailable`, plus the reader's own `error` string **surfaced, never
  swallowed**. Do not paraphrase the error into a friendlier sentence that loses what failed.
- **Axis 3 — some but not all of what this duty needs came back readable.** Per duty, and only
  where the row names a case. ⛔ **Where a row says no partial case is named, that is the answer —
  report it as un-named, never fill it with a plausible guess.** An invented partial rule is a
  fabricated contract that a future session will build on.

**Axis 3 is where the per-row wording matters most**, because the honest shapes differ: a
permanent structural null with its reason attached (`days_remaining`, sealed feed rate), a
per-row unknown that must not fold into a farm-wide null (an untraded station, an unreadable
vehicle's damage), and a `null` reward that must never render as a real `$0`. Read the row.

## ⛔ A blocked input is never aggregated

If a duty's input carries a `blocked_by` marker, **emit it as blocked — do not aggregate it, do
not re-derive it, and do not compute around it.** The blocked derivations are `sum`, `total`,
`cumulative`, `mean` and `rate`; producing any of them from a blocked input turns a known-wrong
figure into a confident one, which is worse than reporting the block.

Today this lands on **D-16** (decide whether to buy land), whose `cost_reconciliation_status` is
blocked. D-16 is an **`escalate: true`** duty, so the block travels into S5's escalation path
rather than being quietly dropped from a card. Render it as blocked with its reason, or omit the
field — **never as a computed comparison.** `references/blocked-capabilities.json` is the single
authority for what is blocked; read it rather than inferring from a missing value.

## The output is a schema, not a card

Emit each duty's `output_schema` as **structured output**. The rendering — a card, a board column,
a future UI — is a **consumer** of that schema and never its author. Evaluate all 16 rows before
composing anything: S5 ranks and splits them, and it can only do that if every duty has already
reported, including the ones reporting nothing.

## Next

Once every admissible duty has been evaluated and emitted, read fully and follow: {nextStepFile}
