---
class: dossier
load: C
owns: "what each owned storage node can structurally ACCEPT — stable until a node/mod changes"
cap_lines: 80
cap_kb: 8
rotation_trigger: none
archive_target: N/A
reconciliation: "rows update in place when a node is added/rebuilt or a mod changes; unresolved categories are 'unknown', never 'no'"
format_version: 1
parity_spec:
  required_sections: ["## What each storage node accepts", "## Unresolved / unknown"]
---

# Storage capability

_What each owned storage node can **accept** — not what it currently holds (that's live, via
`read_placeables.py`). Resolving this requires reading **both** `fillTypes` **and**
`fillTypeCategories` per node, then expanding categories against base + map + mod `fillTypes.xml`
definitions (friction-log F-102, F-116) — this is exactly the check that got "no silo accepts
onion" wrong by only looking at one attribute. Genuinely durable: what a node can accept doesn't
change session-to-session — re-verify an entry only when a new mod is added or a node is
rebuilt/upgraded._

_Populating this cheaply and reliably needs a dev-side script (`read_storage_capability.py`, per
F-116's "Fix needed") that reads both attributes; until it ships, rows here are resolved by hand._

## What each storage node accepts

| Storage node | Declared via | Accepts | Resolved how | Last verified |
|---|---|---|---|---|
| {{NAME/ID}} | {{`fillTypes` attr \| `fillTypeCategories` attr \| both}} | {{expanded fill-type list}} | {{base game \| map \| mod:<name> — cite the file}} | {{DATE}} |

## Unresolved / unknown

{{Any node where category expansion couldn't be completed — report `unknown`, never assume a
category is empty just because its definition wasn't found (`references/reading-the-save.md`:
"absence must never be allowed to look like data"). A node with `fillTypeCategories` but no
`fillTypes` is **not** "unrestricted" — it means the category still has to be expanded. Treat every
unresolved category as `unknown`, not `no`, until the expansion is actually done.}}
