# sanctum/state/production-dossiers/

_This directory holds one dossier per production chain this farm owns and has
something worth remembering about. Each file uses the shape in
`templates/production-dossier.md`._

**What goes here:** one file per chain, named `production-{{id}}.md` (matching the
building id from the save), created the first time a chain's durable facts are
worth recording — not pre-created for every chain on onboarding. The
`state/production-roster.md` is the index of chains owned; these are the per-chain detail.

**What must NOT go here:** live input/output fill, running/idle status, or
efficiency — those are answered fresh every session by `read_placeables.py` /
`farm_snapshot.py`. A dossier holds durable facts (typical consumption rate, best
sell point, a chain quirk) and an append-only History table, never a cached
"current state" (friction-log F-117).

**History sidecars:** when a dossier's History table would push it over cap, the
oldest rows relocate verbatim into a sibling `production-{{id}}-history.md` in this
same directory (uncapped), leaving a one-line pointer in the dossier. Never
summarize a relocated row.

This README is a skill-authoring note, not sanctum content -- it documents what
belongs in this directory but is not itself a chain record.
