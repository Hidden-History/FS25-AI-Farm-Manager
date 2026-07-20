# Sanctum upkeep — what each file is, and when it changes

The sanctum is the farm's memory. This is the per-file reference for keeping it honest:
what lives in each file, when it changes, and what must never be skipped.

Read this **at closeout**, and any time you're unsure whether something you just learned
belongs in a file rather than only in the conversation. The conversation ends; the sanctum
is what survives it.

## The rule that matters most

**Write as you go, not in a batch at the end.** Closeout's job is to *verify* the sanctum is
current, not to reconstruct a whole session from memory — memory is exactly what's worst at
the end of a long session. If a closeout is doing lots of writing, the session was doing too
little.

And a closeout is not optional bookkeeping: `history/closeout-latest.md` is the only thing next
session's briefing has to diff against. A session that ends without one is a session that
never happened, as far as the farm's memory is concerned.

## Keeping it bounded — the upkeep tool

`scripts/sanctum_maintain.py` is the parity/upkeep tool. `check` reports each file FRESH / STALE /
UNVERIFIABLE — an over-cap file comes back **STALE**, and that is your tripwire to rotate. `reconcile`
migrates an old-version file to the current template shape, content-preserving. `rotate` handles the
mechanical cases automatically (the ledger's segment-and-retain, the journal's rolling window, a
dossier's on-cap `## History` relocation).

For everything else — a directive that closed, a sold machine, a resolved friction — **rotation is your
job, per each file's own `## Rotation` / reconciliation line** (move the closed entry whole to its
archive, never blind-delete). When `rotate` reports `action: "agent-rotation"`, that is not a failure —
it means the file is one you rotate by hand per its instructions. `check`'s STALE is the signal; the
template tells you how.

## Every file, and when it changes

| File | When it changes |
|---|---|
| `history/closeout-latest.md` | **Every closeout** — overwritten with the new closeout. This is what next session reads. |
| `history/friction-log.md` | **Every closeout — APPENDED, never overwritten.** Every issue, error, and friction: your own analysis errors, script bugs, silent wrong answers, missing tooling, portable docs asserting farm-specific facts, and anything the player had to tell you twice. See `templates/friction-log.md`. **This is not a duplicate of the closeout's "What didn't work"** — that section is per-session and gets overwritten; this is the standing defect list that accumulates until things are actually fixed. The skill cites friction IDs (`F-001`, `F-010`, `F-023`…) as load-bearing evidence; those citations are worthless if no log exists. |
| `history/journal/{{date}}-session-{{n}}.md` | **Every closeout** — a new archive entry, same content as above. Archive is history; `history/closeout-latest.md` is the handoff. Writing only one of the two silently breaks one of them. |
| `state/finances-ledger.md` | Row **appended at Session Start** (opening snapshot); closeout **completes that row's Notes**. **Never a second row** — see below. |
| `state/field-dossiers/field-{id}.md` | Whenever a field's state materially changes or you learn something worth remembering. Create from `templates/field-dossier.md` if new. Verify at closeout. |
| `identity/directives.md` | Whenever a long-term plan is set, changed, or completed (`templates/directive-entry.md` for new entries). Verify at closeout. |
| `state/equipment-roster.md` | When equipment is bought, sold, repaired, or flagged for repair. Verify at closeout. |
| `state/equipment-shopping-list.md` | When wanted iron changes, or you look up a price — **log the price** so the lookup is never repeated. |
| `state/field-price-watchlist.md` | When a parcel becomes interesting, or you resolve its area/cost. |
| `state/husbandry-roster.md` | When animals are added, sold, or moved, or a building's state materially changes. |
| `state/production-roster.md` | When a chain is started, stopped, or its inputs/outputs change. |
| `config.json` | Rarely — only if a path or the farm name changed. **`session_count` increments at Session Start; never increment it again at closeout.** |
| `identity/creed.md` | Rarely — identity and tone. Changing it needs the player's say-so, not your inference. |
| `identity/decision-making.md` | Rarely — this farm's judgment. Same rule: the player's call, never yours alone. |

If a file didn't change, that's fine — say nothing. Don't touch a file just to prove you
looked at it; a no-op edit is noise a future session has to read past.

## The ledger row: opened at start, completed at closeout, never appended twice

`state/finances-ledger.md` gets **one row per session, appended at Session Start** as that
session's *opening* snapshot — so a session that ends abruptly still left evidence. Closeout
**completes that same row's Notes** (what moved and why) and appends nothing.

Every row being an opening figure is what makes the trend meaningful: it's measured
open-to-open, so every row is comparable. A second row at closeout would put opening and
closing figures in the same column, and a trend line built from a column that means two
different things on different rows is worse than no trend line — because it still looks like
one.

A session's *achievement* is therefore read two ways, neither of them another ledger row:

- **The delta to the next session's row** — the ledger's job is the trend across sessions.
- **The closeout narrative and its journal archive** — the journal's job is what actually
  happened, in prose, with the reasoning.

One caveat worth saying out loud if it matters: if the player plays *without* the manager
between sessions, that movement lands in the next row's opening and reads as though it
belonged to the session. The ledger measures elapsed farm, not attributed effort.

`templates/finances-ledger.md` states the same rule as the file's own guide. If it, this
file, and SKILL.md ever disagree, that's a bug in one of them, not a choice.

## What didn't work

The closeout template's "What didn't work" section is the highest-value thing in the whole
sanctum, and the easiest to quietly ruin. Fill it honestly — a recommendation that missed, a
contract that wasn't worth it, a sell timed badly. It's what stops next session repeating the
mistake.

Don't skip it, and don't pad it. **"Nothing missed today" is a valid entry; an invented
failure is not.** A fabricated lesson is worse than no lesson, because a future session will
act on it.
