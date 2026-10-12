#!/usr/bin/env python3
"""Record the player's merged-field answer and clear the "not yet assessed" marker.

    python3 record_field_merges.py <dossier_dir> --none
    python3 record_field_merges.py <dossier_dir> --config <sanctum>/config.json \\
        --merge <CANONICAL> <OTHER_ID> [...] [--merge ...] [--planned <CANONICAL> <OTHER_ID> [...]]
    python3 record_field_merges.py <dossier_dir> --config <sanctum>/config.json --single <FIELD> [...]

SPEC-livetest-fixes-2026-09-18 F11(2) / BUG-036. `read_field_merges.py` refuses
while `_UNASSESSED.md` is present, and the FIELDS tab is never published -- but
nothing ever asked the player about merges, so the marker never cleared. The
question is onboarding O3's (and S2's while the marker is present); THIS script
writes the answer, so the dossier merge-line grammar lives in code, never in an
LLM's formatting.

`--single FIELD...` writes (or re-stamps) the dossier of an ORDINARY, unmerged field: its size
line becomes `Single field — not merged.` so the manager never types that marker by hand. An
existing free-form size line is kept after the marker and as a dated History row. It needs the
merged-fields question already answered (--none/--merge/--planned): a single-field dossier
cannot be validated while the directory is still "not assessed", and it never clears that marker.

Each id list is `CANONICAL OTHER...`: the first id is the one the merged field
reports as, and it is one of the parcels. `--merge` records a merge already made
in game; `--planned` one the player intends to make (never collapsed).

⛔ EVERY ID IS CHECKED AGAINST THE SAVE. `--config` names the savegame, and each
id must be a <field> in its fields.xml (the map's own field list, which the
FIELDS rows cover). An unknown id refuses the whole answer: a mistyped id would
otherwise become a field the map does not have.

⭐ AN EXISTING DOSSIER IS UPDATED, NEVER REPLACED. On an existing farm the
canonical field usually already has a dossier holding its history. Only its
`**Size / notes:**` line is replaced (or inserted, if it has none), and the line
it replaces is kept as a dated row in the dossier's History. Nothing else in the
file changes, and the output names every file updated and its previous line.

⛔ FAIL LOUD, NEVER HALF-DONE. Every dossier touched is re-read through
read_field_merges.py's own parser and collision check before the marker is
removed; on any failure every file this run touched is restored byte for byte,
the marker is restored, and the result is `{"error": ...}` with exit 1.

Writes only under <dossier_dir> (the sanctum). Reads the savegame; never writes it.
"""
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import read_field_merges  # noqa: E402
from xml_utils import load_xml  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "templates", "field-dossier.md")
USAGE = ("usage: record_field_merges.py <dossier_dir> --none | <dossier_dir> --config "
         "<sanctum>/config.json --merge CANONICAL OTHER [...] [--merge ...] "
         "[--planned CANONICAL OTHER [...]] | <dossier_dir> --config <sanctum>/config.json "
         "--single FIELD [...]")
SIZE_PREFIX = read_field_merges.SIZE_LINE_PREFIX


def _fail(message, **extra):
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    return 1


def parse_args(argv):
    """Returns (dossier_dir, config, none, [(state, [ids])]) or raises ValueError."""
    if not argv or argv[0].startswith("-"):
        raise ValueError(USAGE)
    dossier_dir, rest = argv[0], list(argv[1:])
    config, none, merges, current = None, False, [], None
    while rest:
        token = rest.pop(0)
        if token == "--none":
            none, current = True, None
        elif token == "--config":
            if not rest:
                raise ValueError("--config given with no path. " + USAGE)
            config, current = rest.pop(0), None
        elif token in ("--merge", "--planned"):
            current = ("completed" if token == "--merge" else "planned", [])
            merges.append(current)
        elif token == "--single":
            current = ("single", [])
            merges.append(current)
        elif current is not None and re.fullmatch(r"\d+", token):
            current[1].append(int(token))
        else:
            raise ValueError("unexpected argument %r. %s" % (token, USAGE))
    if none == bool(merges):
        raise ValueError("give exactly one of --none or at least one --merge/--planned. "
                         + USAGE)
    expanded = []
    for state, ids in merges:
        if state == "single":
            if not ids or len(set(ids)) != len(ids):
                raise ValueError("--single needs one or more distinct field ids; got %r" % ids)
            expanded.extend(("single", [i]) for i in ids)
            continue
        if len(ids) < 2 or len(set(ids)) != len(ids):
            raise ValueError("each merge needs a canonical id and at least one more "
                             "distinct parcel id; got %r" % ids)
        expanded.append((state, ids))
    merges = expanded
    if merges and not config:
        raise ValueError("--config is required with --merge/--planned: every id is checked "
                         "against the savegame's fields.xml. " + USAGE)
    return dossier_dir, config, none, merges


def map_field_ids(config_path):
    """(set_of_field_ids, None) from the savegame's fields.xml, or (None, error)."""
    try:
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, "could not read %s: %s" % (config_path, exc)
    savegame = ((config.get("paths") or {}).get("savegame_dir")
                or config.get("savegame_path"))
    if not savegame or "{{" in str(savegame):
        return None, "%s names no savegame (paths.savegame_dir)" % config_path
    root, err = load_xml(os.path.join(savegame, "fields.xml"))
    if root is None:
        return None, (err or {}).get("error", "fields.xml could not be read")
    ids = {int(f.get("id")) for f in root.iter("field")
           if (f.get("id") or "").isdigit()}
    if not ids:
        return None, "%s lists no <field> ids, so no id can be checked" % savegame
    return ids, None


def size_line(state, ids):
    if state == "single":
        return "Single field \u2014 not merged."
    canonical, n, listed = ids[0], len(ids), ", ".join(str(i) for i in ids)
    if state == "completed":
        return ("Merged field — physically one field in-game, spans %d savegame field "
                "IDs: **%s**. Report any of these %d IDs as field #%d." % (n, listed, n, canonical))
    return ("**PLANNED merge, not yet done in-game.** Currently %d separate savegame "
            "field IDs — **%s**. The player intends to combine them into one field #%d; "
            "until then treat and report them as %d separate fields." % (n, listed, canonical, n))


def render_new(template, state, ids, today):
    canonical = ids[0]
    what = ("worked as one merged field #%d" if state == "completed"
            else "planned as one merged field #%d") % canonical
    event = ("Merge recorded from the player's answer: parcels %s %s "
             "(record_field_merges.py)." % (", ".join(str(i) for i in ids), what))
    if state == "single":
        event = "Dossier created for an ordinary, unmerged field (record_field_merges.py --single)."
    fills = {
        "FIELD_ID": str(canonical),
        "SIZE_OR_MAP_NOTES": size_line(state, ids),
        "DATE —": "not recorded (dossier written by record_field_merges.py on %s)" % today,
        "Quirks,": "None recorded yet.",
        "DATE": today,
        "EVENT": event,
        "ANYTHING_WORTH_REMEMBERING": "None yet.",
    }

    def fill(match):
        body = match.group(1)
        for key, value in fills.items():
            if body == key or body.startswith(key + " "):
                return value
        raise KeyError(body[:60])

    text = re.sub(r"\{\{(.*?)\}\}", fill, template, flags=re.S)
    if "{{" in text or "}}" in text:
        raise KeyError("unfilled placeholder")
    return text


def update_existing(text, state, ids, today):
    """Replace (or insert) ONLY the size line; keep the old one as a History row.
    Returns (new_text, previous_line_or_None)."""
    lines = text.split("\n")
    new_line = "%s %s" % (SIZE_PREFIX, size_line(state, ids))
    previous = None
    for i, line in enumerate(lines):
        if line.startswith(SIZE_PREFIX):
            previous = line
            kept_note = previous[len(SIZE_PREFIX):].strip()
            # A free-form line is the player's own size or map note: keep it after the marker.
            # A line that was a merge (or already single) carries nothing to keep.
            # The single marker is matched at the START of the note only (as the reader does): a
            # note that merely mentions "single field" later is the player's own and is kept.
            if state == "single" and kept_note and not (
                    re.search(r"Merged field|PLANNED merge", kept_note, re.I)
                    or re.match(r"single[\s\-\u2013\u2014]*field", kept_note, re.I)):
                new_line = "%s %s %s" % (SIZE_PREFIX, size_line(state, ids), kept_note)
            lines[i] = new_line
            break
    else:
        heading = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
        at = heading + 1 if heading is not None else len(lines)
        lines[at:at] = ["", new_line]
    kept = (previous[len(SIZE_PREFIX):].strip() if previous else "none")
    what = "Single-field line stamped" if state == "single" else "Merge recorded"
    row = "| %s | %s by record_field_merges.py (parcels %s). Previous size " \
          "line: %s |" % (today, what, ", ".join(str(i) for i in ids), kept.replace("|", "\\|"))
    hist = next((i for i, line in enumerate(lines) if line.startswith("## History")), None)
    if hist is None:
        lines += ["", "## History", "", "| Date | Event |", "|---|---|", row]
    else:
        last = hist
        for j in range(hist + 1, len(lines)):
            if lines[j].startswith("## "):
                break
            if lines[j].startswith("|"):
                last = j
        if last == hist:
            lines[hist + 1:hist + 1] = ["", "| Date | Event |", "|---|---|", row]
        else:
            lines.insert(last + 1, row)
    return "\n".join(lines), previous


def _restore(originals):
    """originals: {path: original_text_or_None}. None means the file was new."""
    for path, text in originals.items():
        if text is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)


def _ids_held_by_merges(dossier_dir):
    """{parcel id: dossier file} for every parcel named by a completed or planned merge line.
    Unreadable dossiers are skipped here: collect() refuses them later, and a free-form line
    is exactly what --single exists to re-stamp."""
    held = {}
    for path in sorted(glob.glob(os.path.join(dossier_dir, "field-*.md"))):
        parsed = read_field_merges._parse(path)
        if "error" in parsed or parsed["state"] == "single":
            continue
        for sub in parsed["sub_ids"]:
            held[sub] = parsed["file"]
    return held


def main(argv):
    try:
        dossier_dir, config, none, merges = parse_args(argv)
    except ValueError as exc:
        return _fail(str(exc))
    if not os.path.isdir(dossier_dir):
        return _fail("no such dossier directory: %s" % dossier_dir)

    if merges:
        known, err = map_field_ids(config)
        if err:
            return _fail("cannot check the ids against the save, so nothing was written: "
                         "%s. Remedy: pass the farm's sanctum/config.json with a readable "
                         "savegame." % err)
        unknown = sorted({i for _s, ids in merges for i in ids} - known)
        if unknown:
            return _fail("field id(s) %s are not fields of this save's map (fields.xml), so "
                         "nothing was written. Remedy: ask the player for the field numbers "
                         "exactly as the game shows them." % unknown, unknown_ids=unknown)

    marker = os.path.join(dossier_dir, read_field_merges.UNASSESSED_MARKER)
    marker_text = None
    if os.path.exists(marker):
        with open(marker, encoding="utf-8") as handle:
            marker_text = handle.read()
    only_singles = bool(merges) and all(state == "single" for state, _ids in merges)
    if only_singles and marker_text is not None:
        # Recording an ordinary field must neither clear the "not assessed" marker (the merged-
        # fields question has not been answered) nor be validated while it stands.
        return _fail("the merged-fields question has not been answered for this farm "
                     "(%s is still here), so nothing was written. Remedy: ask the player and "
                     "record his answer first (--none, or --merge/--planned), then --single."
                     % read_field_merges.UNASSESSED_MARKER)

    held = _ids_held_by_merges(dossier_dir)
    clash = {i: held[i] for state, ids in merges if state == "single" for i in ids if i in held}
    if clash:
        # --single would dissolve a completed merge (or stamp a merged parcel "Single field").
        return _fail("field id(s) %s already belong to a merge recorded in the dossiers (completed "
                     "or planned), so nothing was written. Remedy: a merged parcel is not a "
                     "single field; ask the player, and change a merge only with --merge or "
                     "--planned, never --single."
                     % ", ".join("%d (held by %s)" % (i, clash[i]) for i in sorted(clash)),
                     merge_held_ids=sorted(clash))

    originals, written, updated = {}, [], []
    if merges:
        with open(TEMPLATE, encoding="utf-8") as handle:
            template = handle.read()
        today = datetime.date.today().isoformat()
        for state, ids in merges:
            path = os.path.join(dossier_dir, "field-%d.md" % ids[0])
            if path in originals:
                _restore(originals)
                return _fail("field %d is named as the canonical id of two merges; nothing "
                             "was written. Remedy: give each merged field once." % ids[0])
            if os.path.exists(path):
                with open(path, encoding="utf-8", newline="") as handle:
                    original = handle.read()
                originals[path] = original
                text, previous = update_existing(original, state, ids, today)
                updated.append({"file": os.path.basename(path),
                                "previous_size_line": previous})
            else:
                originals[path] = None
                try:
                    text = render_new(template, state, ids, today)
                except KeyError as exc:
                    _restore(originals)
                    return _fail("templates/field-dossier.md carries a placeholder this "
                                 "script does not know (%s); nothing was written." % exc)
                written.append(os.path.basename(path))
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            parsed = read_field_merges._parse(path)
            if "error" in parsed or parsed["sub_ids"] != ids or parsed["state"] != state:
                _restore(originals)
                return _fail("the dossier for field %d does not read back as the merge asked "
                             "for, so every file was restored as it was. Remedy: check "
                             "field-%d.md's frontmatter (format_version, parity_spec)."
                             % (ids[0], ids[0]), parsed=parsed)

    if marker_text is not None:
        os.remove(marker)
    result = read_field_merges.collect(dossier_dir)
    if "error" in result:
        _restore(originals)
        if marker_text is not None:
            with open(marker, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(marker_text)
        return _fail("the dossier directory does not read cleanly with this answer "
                     "recorded, so every file was restored%s: %s"
                     % (" and the marker is back" if marker_text is not None else "",
                        result["error"]), detail=result)

    already = result.get("count", 0)
    if none:
        answer = ("no merged fields" if already == 0 else
                  "no new merges; the dossiers already record %d merge(s), and those WILL "
                  "be applied" % already)
    else:
        answer = "single-field dossiers recorded" if only_singles else "merges recorded"
    payload = {
        "status": "ok",
        "answer": answer,
        "written": written,
        "updated": updated,
        "marker_removed": marker_text is not None,
        "merges": result,
        "next": "the next refresh publishes the FIELDS tab with these merges",
    }
    if none and already:
        payload["warning"] = ("the player answered 'none', but %d merge(s) are recorded in "
                              "the dossiers -- confirm them with the player" % already)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
