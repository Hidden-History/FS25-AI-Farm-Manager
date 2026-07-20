# sanctum/state/husbandry-dossiers/

_This directory holds one dossier per animal building this farm owns and has
something worth remembering about. Each file uses the shape in
`templates/husbandry-dossier.md`._

**What goes here:** one file per building, named `husbandry-{{id}}.md` (matching
the building id from the save), created the first time a building's durable facts
are worth recording — not pre-created for every building on onboarding. The
`state/husbandry-roster.md` is the index of buildings owned; these are the per-building
detail.

**What must NOT go here:** live fill/count/health figures — those are answered
fresh every session by `read_placeables.py` / `farm_snapshot.py`. A dossier holds
durable facts (feed supplier, observed consumption rate, sell-price patterns) and
an append-only History table, never a cached "current state" (friction-log F-117).

**History sidecars:** when a dossier's History table would push it over cap, the
oldest rows relocate verbatim into a sibling `husbandry-{{id}}-history.md` in this
same directory (uncapped), leaving a one-line pointer in the dossier. Never
summarize a relocated row.

This README is a skill-authoring note, not sanctum content -- it documents what
belongs in this directory but is not itself a building record.
