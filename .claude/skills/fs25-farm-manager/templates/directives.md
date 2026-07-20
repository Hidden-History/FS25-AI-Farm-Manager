---
class: register
load: B
owns: "this farm's standing long-term plans/directives — open, paused, and recently-closed"
cap_lines: 120
cap_kb: 6
rotation_trigger: age-or-cap
archive_target: "history/archive/directives-{YYYY}.md"
reconciliation: "OPEN/active entries are the live slice; closed entries relocate whole (never deleted) with a dated pointer"
format_version: 1
parity_spec:
  required_sections: ["## How entries accumulate", "## Closing a directive honestly", "## Rotation — moving closed entries to cold storage"]
---

# Standing Directives

_This file is the farm's memory for anything that spans more than one session: a
long-term goal, a plan you're partway through, an open question that's waiting on
the player. A briefing should check this file every session and say something if
an entry is due for review -- that's the whole point of writing it down instead of
letting it live only in the conversation that created it._

_No directives yet. Add long-term plans here as they're agreed on -- use
`directive-entry.md` for the shape of a single entry._

## How entries accumulate

Append a new entry (from `directive-entry.md`) whenever a plan, goal, or open
question is meant to outlive this session -- not for anything that gets resolved
before closeout. Newest or most-active entries first is a reasonable ordering, but
consistency matters more than the exact rule.

Every entry carries the same fields, and none of them are optional:
- **Status** -- `active`, `paused`, `done`, or `abandoned`. Never leave this
  implicit in the prose; a reader scanning statuses should be able to tell what's
  live without reading the goal text.
- **Set on** -- when the directive was created.
- **Goal** -- what success looks like, in one or two sentences.
- **Plan** -- what has to happen, or what's being watched for.
- **Review when** -- the trigger that should surface this again (a date, an
  event, "every session," or "the player decides").
- **Last touched** -- date and what changed, updated every time the entry is
  touched, even if the change is "reviewed, nothing new."

**If a fact a directive depends on isn't known yet, say `unknown` in the entry
rather than skipping the field or guessing a plausible-sounding value.** A missing
number reads as "not yet needed"; an `unknown` reads as "checked, and it isn't
answerable yet" -- those are different states and this file should distinguish them.

## Closing a directive honestly

When a directive resolves, don't delete it -- strike the title and mark it closed,
then write what **actually** happened, even if that contradicts what the directive
assumed when it was opened. A directive that turns out to have been wrong about its
own premise (e.g. it was opened as "blocking" and later turns out never to have
been blocked at all) is exactly the kind of thing worth keeping a record of --
closing it quietly would erase the lesson along with the open item. Illustrative
shape:

```
### ~~Confirm whether the north silo's foundation needs repair before filling it~~ — CLOSED
- **Status:** ✅ done {{DATE}} — and it was never actually blocking.
- **Outcome:** Foundation is sound; no repair needed.
- **What actually happened:** This was opened as "blocking" on the assumption a
  structural check was required before the silo could be used. It wasn't --
  the concern turned out to be based on a different building. The silo has been
  usable the whole time.
- **Lesson:** Before flagging something as blocking, check it directly rather
  than reasoning from a similar-looking case.
```

A directive that simply succeeds as planned still deserves the same honesty in
**Outcome** and **What actually happened** -- "worked as planned" is a fine answer
when true, but say so explicitly rather than leaving the reader to infer it from
the status flipping to done.

## Rotation — moving closed entries to cold storage

This file is loaded at every briefing, so it can't grow without bound. Closed entries
are relocated to cold storage, never deleted -- nothing is lost, only moved.

- **Trigger (`age-or-cap`):** on session close, if this file is over `cap_lines`/`cap_kb`,
  **or** a `done`/`abandoned` entry has been closed for more than one full in-game season
  with no further touch -- whichever comes first.
- **What never rotates:** `active` and `paused` entries -- a live plan is never swept away
  mid-review. Only `done`/`abandoned` entries are rotation-eligible.
- **Mechanism:** move the closed entry's full text, unedited (its Outcome / What actually
  happened / Lesson fields are exactly what's worth keeping), to
  `history/archive/directives-{{YYYY}}.md`, and replace it here with one dated pointer line:
  `- _[archived {{DATE}}] "{{TITLE}}" ({{N}} lines) → history/archive/directives-{{YYYY}}.md_`.
- **Conservation:** the archive file is append-only and kept in full; only the
  always-loaded live file sheds bulk. Prove nothing is lost before writing (the
  archive-not-delete discipline).
