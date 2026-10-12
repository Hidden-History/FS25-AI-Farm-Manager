#!/usr/bin/env python3
"""Write the per-field crop plan: `<sanctum>/state/field-plan.md`.

    python3 record_field_plan.py <sanctum_dir> [--set FIELD CROP WINDOW]... \\
        [--reviewed FIELD...] [--reviewed-all] [--remove FIELD...]
    python3 record_field_plan.py <sanctum_dir> --show

SPEC-livetest-fixes-2026-10-01 item 3 / DEC-256. The manager builds this plan itself,
keeps it current, and reviews it with the player. THIS script writes it, so the table
grammar lives in code and never in an LLM's formatting (the pattern of
record_field_merges.py). Format contract: `references/field-plan-format.md`.

  --set FIELD CROP WINDOW   upsert one row (repeatable). A set that changes nothing
                            is a no-op and keeps the row's Reviewed answer; a set that
                            changes the crop or window records today as Planned on and
                            resets Reviewed to `no`: the player reviewed the OLD plan.
  --reviewed FIELD...       the player has reviewed these rows (each must exist)
  --reviewed-all            ... every row
  --remove FIELD...         drop these rows (each must exist). Exempt from the save checks
                            below, so a stale row (the field left the map, or was merged into
                            another) can always be removed.
  --player-confirms-owned   let a --set through for a field whose OWNERSHIP the skill could not
                            resolve (a base-game map, no mods dir). Never lets through a field
                            the farm provably does not own.
  --show                    read-only: print the store (read_field_plan.collect)

⛔ EVERY ID IS CHECKED AGAINST THE SAVE. `<sanctum>/config.json` names the savegame and
each id must be a <field> in its fields.xml. ⛔ AND AGAINST THE MERGE TABLE: a field the
player has merged is ONE row keyed by its canonical id (the id the merge dossier names),
so a parcel id of a completed merge is refused with the canonical id named. A planned
merge is not collapsed, so its parcels are separate rows.

⛔ A ROW IS NEVER REVIEWED BY THE CALL THAT WRITES IT. `--reviewed` names a row the player has
already seen; naming a field this same call created or changed is refused, and
`--reviewed-all` skips such rows and lists them. ⛔ A FIELD THE FARM DOES NOT OWN IS REFUSED
(ownership as emit_fields_xml.py resolves it: read_farmland_areas.py, spatial join); where
ownership cannot be resolved the refusal says so and names --player-confirms-owned.

⛔ FAIL LOUD, NEVER HALF-DONE. The file is written atomically, re-read through
read_field_plan.py, and restored byte for byte if it does not read back as asked. Any
refusal is `{"error": ...}` on stdout, exit 1, and nothing is written. A sanctum that
has no plan file gets one made from templates/field-plan.md.

Writes only `<sanctum>/state/field-plan.md`. Reads the savegame; never writes it.
"""
import datetime
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import read_field_merges  # noqa: E402
import read_field_plan  # noqa: E402
from record_field_merges import map_field_ids  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "templates", "field-plan.md")
USAGE = ("usage: record_field_plan.py <sanctum_dir> --show | <sanctum_dir> "
         "[--set FIELD CROP WINDOW]... [--reviewed FIELD...] [--reviewed-all] "
         "[--remove FIELD...] [--player-confirms-owned]")


def _fail(message, **extra):
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    return 1


def parse_args(argv):
    """-> (sanctum, show, sets, reviewed, reviewed_all, removes, confirms) or raises ValueError."""
    if not argv or argv[0].startswith("-"):
        raise ValueError(USAGE)
    sanctum, rest = argv[0], list(argv[1:])
    show, reviewed_all, sets, reviewed, removes = False, False, [], [], []
    confirms, current = False, None
    while rest:
        token = rest.pop(0)
        if token == "--show":
            show, current = True, None
        elif token == "--reviewed-all":
            reviewed_all, current = True, None
        elif token == "--player-confirms-owned":
            confirms, current = True, None
        elif token == "--set":
            if len(rest) < 3:
                raise ValueError("--set needs FIELD CROP WINDOW. " + USAGE)
            field = rest.pop(0)
            if not re.fullmatch(r"[1-9]\d*", field):
                raise ValueError("--set field %r is not a field id" % field)
            sets.append((int(field), rest.pop(0), rest.pop(0)))
            current = None
        elif token in ("--reviewed", "--remove"):
            current = reviewed if token == "--reviewed" else removes
        elif current is not None and re.fullmatch(r"[1-9]\d*", token):
            current.append(int(token))
        else:
            raise ValueError("unexpected argument %r. %s" % (token, USAGE))
    asked = [bool(sets), bool(reviewed), reviewed_all, bool(removes)]
    if show and any(asked):
        raise ValueError("--show reads only; it cannot be combined with a write. " + USAGE)
    if not show and not any(asked):
        raise ValueError("nothing asked for. " + USAGE)
    if reviewed_all and reviewed:
        raise ValueError("give --reviewed-all or --reviewed FIELD..., not both")
    for label, ids in (("--set", [s[0] for s in sets]), ("--reviewed", reviewed),
                       ("--remove", removes)):
        if len(set(ids)) != len(ids):
            raise ValueError("%s names a field twice: %s" % (label, sorted(ids)))
    both = {s[0] for s in sets} & set(removes)
    if both:
        raise ValueError("fields %s are both --set and --remove" % sorted(both))
    return sanctum, show, sets, reviewed, reviewed_all, removes, confirms


def render_rows(rows):
    return ["| %d | %s | %s | %s | %s |" % (
        fid, r["crop"], r["window"], r["planned_on"], "yes" if r["reviewed"] else "no")
        for fid, r in sorted(rows.items())]


def rewrite(text, rows):
    """`text` with the table's data rows replaced by `rows`; everything else untouched.

    Every `|` line between the separator and the next `## ` heading is a data row, so a blank
    line a hand edit left inside the table cannot strand later rows below the new ones
    (they would read back as duplicates and fail every later write). Non-table lines in that
    region keep their order and follow the rows."""
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == read_field_plan.SECTION)
    sep = next(i for i in range(start + 1, len(lines))
               if re.fullmatch(r"\|(\s*:?-{3,}:?\s*\|){5}", lines[i].strip()))
    end = next((i for i in range(sep + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    kept = [line for line in lines[sep + 1:end] if not line.lstrip().startswith("|")]
    while kept and kept[0].strip() == "":
        kept.pop(0)
    return "\n".join(lines[:sep + 1] + render_rows(rows) + ([""] if kept else []) + kept
                     + lines[end:])


def owned_fields(sanctum):
    """({field_id: True|False|None}, None) or (None, reason): which fields this farm owns, as
    emit_fields_xml.py resolves it (read_farmland_areas.py). None for a field = unresolved."""
    try:
        with open(os.path.join(sanctum, "config.json"), encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, "config.json could not be read: %s" % exc
    paths = config.get("paths") or {}
    savegame, mods = paths.get("savegame_dir"), paths.get("mods_dir")
    farm = config.get("farm_id")
    farm = int(farm) if str(farm).isdigit() else None
    if not savegame or "{{" in str(savegame) or not mods or "{{" in str(mods) or farm is None:
        return None, ("config.json names no usable savegame_dir, mods_dir or farm_id, so "
                      "read_farmland_areas.py cannot run")
    import emit_fields_xml
    areas, why = emit_fields_xml.collect_areas(savegame, mods, farm)
    if why:
        return None, why
    return {fid: (row.get("owned") if isinstance(row.get("owned"), bool) else None)
            for fid, row in areas.items()}, None


def atomic_write(path, text):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=directory, prefix=".field-plan-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ensure_plan_file(plan_file):
    """Create the plan file from templates/field-plan.md if it is NOT there, for a sanctum made
    before the store existed. Idempotent and NEVER overwrites: exclusive-create, so an existing
    file (even a corrupt one) is left exactly as it is. Returns "created" | "present", or
    {"error": ...}. Called by refresh_state.py before every FIELDS publish, so after it runs a
    missing file is a real fault again and the emitter's `unknown` means what it says."""
    try:
        with open(TEMPLATE, encoding="utf-8") as handle:
            text = handle.read()
        if "error" in read_field_plan.parse(text, "templates/field-plan.md"):
            return {"error": "templates/field-plan.md does not parse, so no plan file was created"}
        os.makedirs(os.path.dirname(plan_file), exist_ok=True)
        with open(plan_file, "x", encoding="utf-8", newline="\n") as out:
            out.write(text)
        return "created"
    except FileExistsError:
        return "present"
    except OSError as exc:
        return {"error": "could not create %s: %s" % (plan_file, exc)}


def main(argv):
    try:
        sanctum, show, sets, reviewed, reviewed_all, removes, confirms = parse_args(argv)
    except ValueError as exc:
        return _fail(str(exc))
    sanctum = os.path.abspath(sanctum)
    if not os.path.isdir(sanctum):
        return _fail("no such sanctum directory: %s" % sanctum)

    if show:
        result = read_field_plan.collect(sanctum)
        print(json.dumps(result, indent=2))
        return 1 if "error" in result else 0

    path = read_field_plan.plan_path(sanctum)
    original = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                original = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            return _fail("the existing plan file could not be read, so nothing was written: "
                         "%s. Remedy: fix or restore %s first." % (exc, path))
        current = read_field_plan.parse(original, os.path.basename(path))
        if "error" in current:
            return _fail("the existing plan file does not read cleanly, so nothing was "
                         "written: %s. Remedy: fix or restore %s first." % (current["error"], path))
        rows = current["rows"]
        base_text = original
    else:
        with open(TEMPLATE, encoding="utf-8") as handle:
            base_text = handle.read()
        seeded = read_field_plan.parse(base_text, "templates/field-plan.md")
        if "error" in seeded:
            return _fail("templates/field-plan.md does not parse, so nothing was written: %s"
                         % seeded["error"])
        rows = {}

    # Every id is checked: against the save's map, then against the merge table. --remove is
    # exempt: a stale row (field gone, or merged later) must always be removable.
    named = sorted({s[0] for s in sets} | set(reviewed))
    if named:
        known, err = map_field_ids(os.path.join(sanctum, "config.json"))
        if err:
            return _fail("cannot check the ids against the save, so nothing was written: %s. "
                         "Remedy: the sanctum's config.json must name a readable savegame." % err)
        unknown = [i for i in named if i not in known]
        if unknown:
            return _fail("field id(s) %s are not fields of this save's map (fields.xml), so "
                         "nothing was written. Remedy: use the field numbers exactly as the "
                         "game shows them." % unknown, unknown_ids=unknown)
        merges = read_field_merges.collect(os.path.join(sanctum, "state", "field-dossiers"))
        if "error" in merges:
            return _fail("the merge table cannot be read, so a field's canonical id cannot be "
                         "checked and nothing was written: %s. Remedy: record the player's "
                         "merged-field answer first (record_field_merges.py)." % merges["error"])
        canonical_of = {sub: canon for canon, subs in merges["completed"].items() for sub in subs}
        not_canonical = {i: canonical_of[i] for i in named
                         if i in canonical_of and canonical_of[i] != i}
        if not_canonical:
            return _fail("field(s) %s are parcels of a completed merge; the plan is keyed by the "
                         "merged field's canonical id, so use %s. Nothing was written."
                         % (sorted(not_canonical), {k: v for k, v in sorted(not_canonical.items())}),
                         canonical_ids=not_canonical)

    today = datetime.date.today().isoformat()
    changed, unchanged = [], []
    for fid, crop, window in sets:
        for label, value in (("crop", crop), ("window", window)):
            why = read_field_plan.check_text("field %d %s" % (fid, label), value)
            if why:
                return _fail("%s, so nothing was written." % why)
        old = rows.get(fid)
        if old and old["crop"] == crop and old["window"] == window:
            unchanged.append(fid)
            continue
        rows[fid] = {"crop": crop, "window": window, "planned_on": today, "reviewed": False}
        changed.append(fid)
    # ⛔ A ROW THE PLAYER HAS NOT SEEN IS NOT REVIEWED: this call created or changed these.
    unseen = sorted(set(reviewed) & set(changed))
    if unseen:
        return _fail("field(s) %s were created or changed by this same call, so the player has "
                     "not reviewed them; nothing was written. Remedy: --reviewed in a later "
                     "call, after he has seen the row." % unseen, not_yet_seen=unseen)
    # ⛔ A FIELD THE FARM DOES NOT OWN IS NOT PLANNED. Only rows this call creates or changes.
    if changed:
        owned, why = owned_fields(sanctum)
        if why is None:
            not_owned = sorted(f for f in changed if owned.get(f) is False)
            unresolved = sorted(f for f in changed if owned.get(f) is None)
        else:
            not_owned, unresolved = [], sorted(changed)
        if not_owned:
            return _fail("field(s) %s are not owned by this farm, so nothing was written."
                         % not_owned, not_owned=not_owned)
        if unresolved and not confirms:
            return _fail("ownership of field(s) %s could not be resolved%s, so nothing was "
                         "written. Remedy: if the player has told you these are his, repeat "
                         "with --player-confirms-owned." % (unresolved,
                         " (%s)" % why if why else ""), ownership_unresolved=unresolved)
    absent = sorted(set(reviewed) | set(removes))
    absent = [i for i in absent if i not in rows]
    if absent:
        return _fail("field(s) %s have no plan row to review or remove, so nothing was written."
                     % absent, no_row=absent)
    marked = sorted(f for f in rows if f not in changed) if reviewed_all else sorted(reviewed)
    for fid in marked:
        rows[fid]["reviewed"] = True
    for fid in removes:
        del rows[fid]

    text = rewrite(base_text, rows)
    try:
        atomic_write(path, text)
    except OSError as exc:
        return _fail("could not write %s: %s" % (path, exc))
    back = read_field_plan.collect(sanctum)
    if "error" in back or back["rows"] != rows:
        if original is None:
            os.remove(path)
        else:
            atomic_write(path, original)
        return _fail("the plan file did not read back as written, so it was restored as it was: "
                     "%s" % back.get("error", "rows differ"))
    print(json.dumps({
        "status": "ok",
        "plan_file": path,
        "created": original is None,
        "changed": changed,
        "unchanged": unchanged,
        "reviewed": marked,
        "skipped_not_yet_seen": sorted(changed) if reviewed_all else [],
        "ownership_unresolved_accepted": sorted(f for f in changed if confirms and (
            owned is None or owned.get(f) is None)) if changed else [],
        "removed": sorted(removes),
        "count": back["count"],
        "unreviewed": back["unreviewed"],
        "next": "the next refresh publishes these rows on the FIELDS tab",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
