# sanctum/history/journal/

_This directory is the permanent archive of every session's closeout. It has
no per-file template of its own -- each entry uses the same shape as
`templates/session-closeout.md`, the one written to `history/closeout-latest.md` at
the end of every session._

**What goes here:** one file per session, named
`{{date}}-session-{{n}}.md`, written at closeout time as a permanent copy of
that session's write-up -- the same content that overwrites
`sanctum/history/closeout-latest.md`. `history/closeout-latest.md` is the single current
snapshot (always overwritten); this directory is the history (always
appended, never overwritten).

**Why both exist:** a briefing only needs the most recent closeout to know
what changed since last time -- that's `history/closeout-latest.md`. But "did this
farm try this contract type before and it went badly" or "how has the debt
trended over ten sessions" needs the full history, which only this directory
holds. Don't skip archiving here even though `history/closeout-latest.md` already has
the same content today -- next session's write will overwrite it.

**Rolling window (rotation):** keep the last **12** session files hot in this directory. At
closeout, move any older ones to `history/archive/journal/{{YYYY}}/` (yearly, farm cadence is low)
-- a move, never a delete. Each per-session file is dossier-class, capped 120 lines / 12 KB (its
size is bounded by `templates/session-closeout.md`'s own 90-line cap, since it's a verbatim copy).

**`INDEX.md`:** one row per session ever, appended each closeout (date | session# | filename |
one-line + cash/debt/land trend) -- so "how has debt trended over ten sessions" is answerable
without opening the archived files. See `INDEX.md` in this directory.

This README is a skill-authoring note, not sanctum content -- it documents
what belongs in this directory but is not itself a session record.
