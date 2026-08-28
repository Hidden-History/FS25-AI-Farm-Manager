---
name: s2-take-delivery
description: 'Receive the gathered state and stop if it is untrustworthy — never assemble it yourself. The trust contract: read the error key, never the exit code.'
nextStepFile: './s3-change-notice.md'
---

# S2: Take delivery of the state

**Progress: Step 2 of 5** — Next: Read the change notice

## First — is the sanctum still true about the save?

**Check the sanctum still matches the save** — before you trust a word of it:
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/check_sanctum_freshness.py" "<savegame_path>"
```
It probes the handful of current-state claims a sanctum legitimately makes (the interest rate,
owned land, the offset, directive premises) and fails when the save contradicts one. **Fix what it
flags before briefing on it** — you are about to speak in the creed's voice, and a stale creed
briefs the player on a farm that no longer exists (F-028). An `unverifiable` verdict is NOT a
pass; read it.

**Migrate the sanctum forward if the mod restructured it.** A mod upgrade can change the
sanctum's structure (e.g. the old `identity/directives.md` folding into `plans/PLAN.md`). Run the
migration applier — it compares the sanctum's `sanctum_schema_version` marker to the version this
skill ships and applies any pending migrations in order:
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/sanctum_maintain.py" migrate "<sanctum_dir>" --apply
```
It backs up the touched subtree to a dated backup dir **before** any write, conservation-proves
nothing is lost, then advances the `sanctum_schema_version` marker. Read the JSON:
- `up_to_date: true` → nothing to do; say nothing to the player.
- one or more `steps` applied → tell the player in **one line** what changed and where the
  backup is: e.g. _"Migrated your plan to the new structure (folded directives into PLAN.md);
  pre-migration backup at `<the step's `backup` path>`."_ (DB-migration-on-launch UX.)
- an `error` (exit code 2 — e.g. `SchemaVersionError` when the marker is ahead of this skill or
  `config.json` is corrupt/unparseable, `MigrationError`, `ConservationError`) → nothing was
  **lost**. Most errors (`SchemaVersionError`, `MigrationError`, corrupt config) fail loud
  *before* any write, so the sanctum is untouched; a `ConservationError` can fire mid-apply after
  a partial write, but the pre-migration backup holds the original and the migration is
  **resumable** (it completes or rolls back on the next briefing).
  **Degrade gracefully: do NOT abort the briefing.**
  Surface the error to the player in one line — e.g. _"Heads-up: couldn't
  finish auto-migrating the sanctum (`<the error text>`); nothing was lost — anything partly
  changed is backed up and will sort itself on the next run. Continuing the briefing; we can look
  at the migration separately."_ Then continue with the rest of session start. **A corrupt config
  or an ahead-version sanctum must never brick every briefing** — it loudly SKIPS migration, not
  the briefing.

## Then — take delivery. You do not assemble THE CACHE's view yourself

```bash
python3 ".claude/skills/fs25-farm-manager/scripts/read_state.py" --config sanctum/config.json
```

**This step runs none of the domain parsers itself to build the cached view.** `read_state.py` is
the cache gate and the only way the CACHE is read; verification is inseparable from that read. Your
job here is to *receive* a view and decide whether it can be trusted — not to gather the cache's own
domains yourself, not to top the cache up with a parser of your own, and not to re-read a cached
domain because a figure looks surprising. **A step that assembles the cache's own state has no one
to hold that state to a contract.**

**The live position — cash, loan, owned land, fleet — is the one named exception, and it comes from
`farm_snapshot.py`, not from hand-picking fields out of the cache above** (s1-orient.md: *"the live
position arrives in S2 and nowhere else"*):
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/farm_snapshot.py" "<savegame_path>" --farm-id <config.farm_id>
```
This is not an exception to "you do not assemble state" — `farm_snapshot.py` is itself a single,
already-vetted composer with its own never-imply-false-by-omission contract (every section states
its own `status`; a missing/errored source is a visible `unavailable`, never a silent gap), read the
same way as the cache: per-section, not by exit code. What the rule above forbids is calling the
*domain parsers* yourself to build or top up the cache's own view — not calling this one, named,
contract-bearing composer for the position.

If the gate refuses, it emits `{"error": ...}` and **zero farm data**. The refusals are distinct
on purpose and must be told apart, because each has a different remedy: `STALE`, `CACHE ABSENT`,
`CACHE EMPTY`, `CACHE VERSION MISMATCH`, `CACHE FARM MISMATCH`. **`CACHE FARM MISMATCH` in
particular means you are pointed at another farm's cache** — never report its contents as this
farm's. The remedy the gate prints (`generate_state.py --config …`) is the caller's decision to
run, not the gate's to do quietly.

## ⛔ The trust contract — four rules, and none of them is the exit code

**① Trust is decided by parsing the emitted JSON for EVERY signal the fleet uses — never by exit
status, and never by `error` alone.** Read the JSON. An exit code is not an outcome here: the
parser fleet is not internally consistent about them — some scripts exit `1` on a failed read and
others exit `0` on the identical failure — so a zero exit is not evidence of data and a non-zero
exit is not evidence of its absence. **`error` is the loudest signal, but the fleet uses at least
three more**: **`calibration_needed`** ("could not confidently parse this source" — a distinct
claim from a section being unresolved, and from `error`); and per-section **`resolved`** /
**`status`** / **`why_unresolved`** — a section can be honestly *unresolved* with no `error` key at
all. **Confirmed case**: `read_fields.py`'s `ownership.resolved: false` + `why_unresolved` ships
with no top-level `error` and `calibration_needed: false` (correct by its own definition) — a
caller checking only `error` reads a clean view of a farm that owns no fields. Check all four
signals, every read. If you cannot parse the output as JSON at all, that is a failure, not an empty
answer.

**② Envelope detection is on `"sections"` — never on `"status"`.** A view that carries a
`"sections"` object is enveloped and each section states its own `status`, `reason` and
provenance. **Do not test for `"status"` to decide this**: the top level carries a `"status"` of
its own, and several unenveloped readers carry one too, so `"status"` is present in both shapes
and distinguishes nothing. Testing it would classify an unenveloped reader as enveloped and read
its fields from the wrong place.

**The top-level `"sections"` entry for a domain is verification metadata, not farm data.** It is
built by the gate itself and carries exactly `domain`, `status`, `reason`, `provenance`,
`cache_entry` and `verification` — nothing else. A `status` of `ok` there is a freshness verdict
about the cache entry: it says the domain's cache is current, not that the domain holds anything,
in either direction. The farm's own figures for that domain render separately, at
`aggregate.domains.<domain>.sections` in the same JSON; reading that path is reading the rest of
the view already delivered to you, not gathering anything of your own, and each section there still
carries the per-section signals rule ① above asks you to check. Open the domain there before
telling the player what it has or lacks — the verification entry was never the place that answer
could live.

**③ A `blocked_by` marker is NOT an error — and its absence of an error does NOT make it
trustworthy.** A block records that a read is **wrong**, which is not the same as a read that
**failed**, and not the same as figures disagreeing. It will arrive with no `error` key at all, so
rule ① will rate it clean — and it is not. **Surface a `blocked_by` distinctly, in its own words**,
never folded into a healthy section and never rendered as a live figure. The single authority for
what is blocked and why is `references/blocked-capabilities.json`; read it rather than inferring.
**Never aggregate or re-derive a blocked figure** — for the live entry the blocked derivations are
`sum`, `total`, `cumulative`, `mean`, `rate`, and computing any of them from a blocked input
launders a known-wrong number into a confident one.

**④ Trust the legacy set whole, or not at all.** For the registered readers that are not
enveloped, there is no per-section partial verdict to compute: **the set is trusted entirely or
rejected entirely.** Do not invent a per-section contract for them. The readers left out are
already named with their reason, and the view declares the omission itself in its
`coverage_note` — *which says what the view covers and says nothing about any domain the cache
layer does not yet generate.* **Carry that note through to the player when it bears on what they
asked**; it is the view's own honesty about its edges, not boilerplate.

## The stop

**If the view cannot be trusted, stop here and say so.** Do not proceed to S3, do not evaluate
duties against a view you have just judged untrustworthy, and do not deliver a briefing with a
caveat attached — a caveat on a briefing gets read past. **Tell the player plainly what refused,
what it means, and the one command that fixes it**, then wait. A briefing built on a rejected view
is worse than no briefing, because it looks exactly like a good one.

`--accept-stale` exists and it **never quietly degrades**: it stamps *every* section — including
the ones that verified clean — `stale`, with a reason. Use it only when the player has been told
the view is not current and has asked for it anyway. **A half-marked view invites trusting the
unmarked half**, which is precisely why the flag marks all of it.

## Then — what the game itself recorded

The parsers read the save; the engine log records what the save never will (a mod that failed to
load, a crash last session):
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/read_game_log.py" "<savegame_path from config.json>"
```
Surface it only when it bears on the farm: any `errors` (especially a **mod-load failure** — a mod
they think is running that silently didn't), or `log_complete: false`, which means the last run
**crashed, was killed, or is still open** — worth a plain word, not a caveat dump. **Zero errors is
a *verified* clean run, not silence; an `{"error": ...}` (no log found) is just "nothing to read,"
never "nothing went wrong."**

## And catch up on fuel/repair alerts

House rule set 2026-07-24 — see `sanctum/config.json` → `house_rules.fuel_and_repair_alerts`. Run
this once here so anything that crossed a threshold while the game was closed gets pushed as an
in-game card now (it pre-sends and shows when the player next loads in):
```bash
python3 ".claude/skills/fs25-farm-manager/scripts/check_fleet_alerts.py" "<savegame_path>" --config sanctum/config.json
```
This write (`sanctum/fleet-alert-state.json`) happens here and from the live watcher loop only.

## Next

Once the state is in hand **and rated trustworthy**, read fully and follow: {nextStepFile}
