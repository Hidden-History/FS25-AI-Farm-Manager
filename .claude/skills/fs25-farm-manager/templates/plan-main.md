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

_This is the farm's one living plan — the single answer to "where does this farm actually
stand, and what's next." It folds together two things that used to live in separate files and
drift apart: a plain-language **Current focus** a player can act on directly, and the
**Standing directives** — the individually-tracked, honestly-closed long-term items that focus
is built from. One file, read at every briefing (it is load-tier B), so there is never a
plan-behind-the-plan to fall out of sync with._

_Empty to start. The first briefing and the first decisions fill it; until then this is shape,
not content._

## Current focus

_The holistic, actionable read — where the farm is right now and what the next moves are, in
the manager's own voice, not a register dump. This is the section a player skims to know what
to do today. **Rewrite it in place each session; never let it accumulate** — it is a synthesis
of the live directives below plus current live state, not a log. The log is the per-session
files in `plans/sessions/` and the journal; if this section is getting long, that length
belongs in a session plan or a dossier, not here._

_Keep it evidence-cited where a claim is load-bearing. The ad-hoc plan this design replaces
earned its trust by citing the save ("owned_count 51→56, cash −$1,158,000 to the dollar"), not
by asserting — do the same. A checklist a player ticks off in-game is fair game here, so is a
crop-rotation table or a delivery order. What does not belong is per-item history — that is
what a directive is for._

{{Write the current focus here — a few short paragraphs, and/or an actionable checklist or
table. Lead with what needs doing next. Cite the save, dossiers, or ledger where a number is
doing work. "Nothing in flight; farm is steady" is a valid focus when it is true.}}

## Standing directives

_The rigorous half: one entry per long-term item — a goal, a plan you are partway through, an
open question waiting on the player. Anything meant to outlive this session lives here as a
tracked entry, so the Current focus above can stay a synthesis and still be traceable to
something honest. Use `templates/directive-entry.md` for the shape of a single entry — that
stencil is the source of truth for the fields and is not restated here._

_Every entry carries the same fields, none optional: **Status** (`active` | `paused` | `done`
| `abandoned` — never left implicit in the prose), **Set on**, **Goal**, **Plan**, **Review
when**, **Last touched**. If a fact an entry depends on is not known yet, write `unknown`
rather than skipping the field or guessing — a missing number reads as "not needed," an
`unknown` reads as "checked, and it is not answerable yet," and those are different states this
file must distinguish._

{{Append directive entries here, newest or most-active first. Copy the shape from
`templates/directive-entry.md`. No directives yet — add them as long-term plans are agreed
with the player.}}

## How entries accumulate

Append a new directive entry (from `directive-entry.md`) whenever a plan, goal, or open
question is meant to outlive this session — not for anything that resolves before closeout.
Newest or most-active first is a reasonable ordering, but consistency matters more than the
exact rule. Each briefing checks this file and says something if an entry is due for review —
that is the whole point of writing it down instead of leaving it in the conversation that
created it.

## Closing a directive honestly

When a directive resolves, do not delete it — strike the title and mark it closed, then write
what **actually** happened, even if that contradicts what the directive assumed when it was
opened. A directive that turns out to have been wrong about its own premise (opened as
"blocking," later never actually blocked at all) is exactly the kind of thing worth keeping a
record of — closing it quietly erases the lesson along with the open item. Illustrative shape:

```
### ~~Confirm whether the north silo's foundation needs repair before filling it~~ — CLOSED
- **Status:** ✅ done {{DATE}} — and it was never actually blocking.
- **Outcome:** Foundation is sound; no repair needed.
- **What actually happened:** This was opened as "blocking" on the assumption a structural
  check was required before the silo could be used. It was not — the concern turned out to be
  based on a different building. The silo has been usable the whole time.
- **Lesson:** Before flagging something as blocking, check it directly rather than reasoning
  from a similar-looking case.
```

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
  `history/archive/plan-{{YYYY}}.md`, and replace it here with one dated pointer line:
  `- _[archived {{DATE}}] "{{TITLE}}" ({{N}} lines) → history/archive/plan-{{YYYY}}.md_`.
- **Conservation:** the archive file is append-only and kept in full; only the always-loaded
  live file sheds bulk. Prove nothing is lost before writing (the archive-not-delete
  discipline). This is agent-rotation: `sanctum_maintain.py rotate` reports `agent-rotation`
  for this file — its directives are prose/list entries, not table rows — which is the signal
  to do the move by hand per this section, not a failure.
