# The field plan store — format contract

SPEC-livetest-fixes-2026-10-01 item 3 (that spec's decision D-1). One file per farm:

    sanctum/state/field-plan.md          (seeded from templates/field-plan.md)

It holds the one thing about a field the save cannot say: **what the player and the manager
plan to grow next.** The FIELDS tab shows it (`emit_fields_xml.py` publishes it, the mod only
displays it).

## What is stored, and what is not

| Column | Meaning |
|---|---|
| `Field` | the **canonical** field id — the id the merge table reports. A completed merge is ONE row; its other parcels have none. A planned (not yet made) merge is not collapsed: its parcels are separate rows. |
| `Next crop` | free text, ≤ 80 characters, no pipe character, no `{`/`}`, no line break |
| `Plant window` | free text, same limits (≤ 80 characters, no pipe character, no braces). The manager writes it in D-02's format, built from the calendar script's period names: `<Early\|Mid\|Late> <season>[ to ...] (game days A–B)`, e.g. `Early spring to mid spring (game days 25–28)`. On a save where seasonal growth is off, exactly `Any time (seasonal growth is off)`, or what the player said, or `timing: ask player`. The writer accepts any text within the limits; the emitter publishes it whole (no cut) and the pane shows it whole. |
| `Planned on` | ISO date the row was last written with a new crop or window |
| `Reviewed` | `yes` once the player has reviewed that row; `no` until then. A changed plan is `no` again. |

**Not stored:** current crop, growth state, harvest-by, anything the save answers live. They
change every session and a stored copy reads as current when it is not (the dossier template's
rule: *no live-state figure is stored*). The emitter reads them from the save.

**Field notes** are NOT in this file. They live in the existing dossier section
`## Notes / quirks` of `state/field-dossiers/field-<id>.md`; there is no second notes store.

## Writing it

Only `record_field_plan.py` writes the table. It checks every id against the save's
`fields.xml` and against the merge table, writes atomically, re-reads what it wrote, and
restores the file if it does not read back. Never edit the table by hand.

    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_plan.py" sanctum --set <FIELD> "<NEXT CROP>" "<PLANT WINDOW>" [--set ...]
    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_plan.py" sanctum --reviewed <FIELD> [<FIELD> ...]
    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_plan.py" sanctum --reviewed-all
    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_plan.py" sanctum --remove <FIELD> [<FIELD> ...]
    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_plan.py" sanctum --show
    python3 ".claude/skills/fs25-farm-manager/scripts/record_field_plan.py" sanctum --player-confirms-owned --set <FIELD> "<NEXT CROP>" "<PLANT WINDOW>"   # ownership unresolved only

`--set` of an unchanged crop and window changes nothing and keeps `Reviewed`. A `--set` that
changes either records today and resets `Reviewed` to `no`.

Rules the writer enforces (each refusal is `{"error": ...}`, exit 1, nothing written):
- **A row is never reviewed by the call that writes it.** `--reviewed N` for a field this same
  call created or changed is refused (the player has not seen it); `--reviewed-all` skips such
  rows and lists them as `skipped_not_yet_seen`.
- **A field the farm does not own is refused**, using ownership as `emit_fields_xml.py` resolves
  it (`read_farmland_areas.py`). Where ownership cannot be resolved (a base-game map, no mods
  dir) the refusal says so; if the player has told you the field is his, repeat with
  `--player-confirms-owned`. That flag never lets through a field the farm provably does not own.
- `--remove` skips the save checks, so a stale row (the field left the map, or was merged into
  another field) can always be removed.
- A non-UTF-8 byte in the file is a structured error, never a traceback.

## Reading it — three answers that must never look alike

`scripts/read_field_plan.py` (one parser, used by the emitter and the writer):

| Answer | Meaning |
|---|---|
| `status: ok`, `count: N` | the file parsed. `count: 0` is a real answer about the PLAN — nothing planned yet — and is also what the seeded file holds. It says nothing about the save. |
| `error` + `missing: true` | no plan file (a sanctum made before the store existed). Not "no plan": we could not ask. `record_field_plan.py` creates the file. |
| `error` | the file is there and does not parse. One bad row refuses the whole answer. |

On the FIELDS tab these become four states for a field: a reviewed row; an unreviewed row;
no row (a gap); and the plan or the field's dossier unreadable (a named unknown with its reason).
