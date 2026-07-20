---
class: register
load: C
owns: "this farm's observed contract payout patterns and taken/skipped decisions — not the live offer board"
cap_lines: 100
cap_kb: 10
rotation_trigger: on-age
archive_target: "history/archive/contracts-archive.md"
reconciliation: "a payout row is written only AFTER a contract resolves (F-025); oldest taken/skipped rows relocate losslessly on age"
format_version: 1
parity_spec:
  required_sections: ["## Payout patterns observed", "## Taken / skipped"]
---

# Contracts — decision log

_This is **NOT** a live contract board — `read_missions.py` / `farm_snapshot.py` answer "what's on
offer right now." This file remembers what a live read can't: payout patterns once a field-tied
contract has actually resolved, and this farm's own reasoning for taking or skipping one. Empty is
correct for a farm that hasn't done contract work yet — say so._

## Payout patterns observed

_Only after a contract has resolved — never a guess pre-accept. A field-tied contract reads
`reward="0"` while on offer and only resolves at accept-time (friction-log F-025): a pre-accept
`0` is **unknown**, not zero. One observation is not a pattern (n=1 — F-101); record the count._

| Contract type | Field/crop class | Observed payout | Observations | Notes |
|---|---|---|---|---|
| {{TYPE}} | {{FIELD_OR_CLASS}} | {{€ once accepted}} | {{N times seen}} | {{anything conditional on this map}} |

## Taken / skipped

_Decisions, not a log of every offer — routine mission-pool churn is not durable signal._

| Date | Contract | Decision | Why |
|---|---|---|---|
| {{DATE}} | {{DESCRIPTION}} | {{taken \| skipped}} | {{reasoning — overlap with own field, equipment fit, deadline, regretted-in-hindsight if relevant}} |

_A per-contract-type dossier (`contracts-dossiers/{{type}}.md`) is worth creating only if a specific
recurring contract type on this farm has a genuine quirk — most farms never need one; don't
scaffold it by default. Once the Taken/skipped table passes ~30 rows, move the oldest verbatim to
`history/archive/contracts-archive.md` (lossless, never summarized — a past decision's reasoning
may matter for a later similar one)._
