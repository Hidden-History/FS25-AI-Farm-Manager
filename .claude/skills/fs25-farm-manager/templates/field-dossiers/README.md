# sanctum/state/field-dossiers/

_This directory holds one dossier per field this farm owns and has something
worth remembering about. Each file uses the shape in
`templates/field-dossier.md`._

**What goes here:** one file per field, named `field-{{id}}.md` (matching the
field id from the save, e.g. `field-71.md`), created the first time a field's
state materially changes or you learn something worth remembering about it --
not pre-created for every parcel on onboarding. A field that's been sitting
untouched with nothing notable about it doesn't need a dossier yet; creating
empty dossiers for every owned parcel just produces files nobody updates.

**When to update an existing dossier vs. create a new one:** update in place
for anything about a field already tracked (planted, harvested, fertilized,
a quirk noticed); only create a new file the first time a given field id
gets its first entry.

**History sidecars:** when a dossier's History table would push it over cap, the
oldest rows relocate verbatim into a sibling `field-{{id}}-history.md` in this
same directory (uncapped), leaving a one-line pointer in the dossier. The sidecar
is the field's full cold history; never summarize a relocated row.

**What belongs in the roster instead:** the full list of which field ids this
farm owns lives in `sanctum/config.json` / `identity/creed.md` (onboarding derives
field ownership once and caches it, since it isn't cheaply re-derivable --
see `references/reading-the-save.md`). This directory is per-field detail,
not the ownership list itself.

This README is a skill-authoring note, not sanctum content -- it documents
what belongs in this directory but is not itself a field record.
