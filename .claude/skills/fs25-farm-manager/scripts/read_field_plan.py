#!/usr/bin/env python3
"""The per-field crop plan, read from the sanctum's `state/field-plan.md`.

    python3 read_field_plan.py <sanctum_dir>

SPEC-livetest-fixes-2026-10-01 item 3 / DEC-256. The plan is a standing duty of
the manager and the FIELDS tab shows it; this is the one parser of the store, shared
by `emit_fields_xml.py` (publishes it) and `record_field_plan.py` (writes it). The
format is `references/field-plan-format.md`.

⛔ NEVER `[]`, `{}` OR None FOR A FAILURE (DEC-001). Three answers, kept apart:
  * `{"error": ..., "missing": true}` -- the file is not there (a sanctum made
    before the store existed). We could not ask. NOT "no plan".
  * `{"error": ...}` -- the file is there and does not parse. One bad row poisons
    the whole answer: a partial plan is not a smaller correct plan, it is rows
    silently shown as "no plan" that the player did plan.
  * `{"status": "ok", "count": 0, "rows": {}}` -- the file parsed and holds no
    rows. That is a REAL answer about the PLAN ("nothing planned yet"), and it is
    also what our own scaffolding seeds. It is never an answer about the SAVE.

⛔ READ-ONLY. Writes nothing, anywhere; the only write is stdout.
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

import datetime
import json
import os
import re
import sys

SCHEMA_VERSION = 1
PLAN_RELPATH = os.path.join("state", "field-plan.md")
SECTION = "## Plan rows"
REQUIRED_FRONTMATTER = "format_version: 1"
HEADER = ("Field", "Next crop", "Plant window", "Planned on", "Reviewed")
MAX_TEXT = 80


def plan_path(sanctum_dir):
    return os.path.join(sanctum_dir, PLAN_RELPATH)


def check_text(label, value):
    """None if `value` can live in a table cell, else the reason. Shared with the writer."""
    if not isinstance(value, str) or not value.strip():
        return "%s is empty" % label
    if value != value.strip():
        return "%s has leading or trailing space" % label
    if re.search(r"[|\r\n\t{}]", value):
        return "%s contains a pipe, a brace or a line break, which the table cannot hold" % label
    if len(value) > MAX_TEXT:
        return "%s is longer than %d characters" % (label, MAX_TEXT)
    return None


def parse(text, name="field-plan.md"):
    """text -> {"rows": {field_id: row}} or {"error": ...}. Never a partial answer."""
    if REQUIRED_FRONTMATTER not in text or "parity_spec:" not in text:
        return {"error": "%s carries no `%s` / `parity_spec:` frontmatter, so it does not "
                         "declare the format this parser reads" % (name, REQUIRED_FRONTMATTER)}
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.strip() == SECTION]
    if len(starts) != 1:
        return {"error": "%s must carry exactly one `%s` section; found %d"
                         % (name, SECTION, len(starts))}
    table = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        if line.lstrip().startswith("|"):
            table.append(line.strip())
    if len(table) < 2:
        return {"error": "%s's `%s` section has no table header, so no row can be read"
                         % (name, SECTION)}

    def cells(line):
        return [c.strip() for c in line.strip("|").split("|")]

    if tuple(cells(table[0])) != HEADER:
        return {"error": "%s's table header is %r, not %r" % (name, cells(table[0]), list(HEADER))}
    if not re.fullmatch(r"\|(\s*:?-{3,}:?\s*\|){5}", table[1]):
        return {"error": "%s's table has no separator row under its header" % name}

    rows = {}
    for line in table[2:]:
        got = cells(line)
        if len(got) != 5:
            return {"error": "%s has a row with %d cells, not 5: %s" % (name, len(got), line)}
        field, crop, window, planned_on, reviewed = got
        if not re.fullmatch(r"[1-9]\d*", field):
            return {"error": "%s has a row whose Field is %r, not a field id" % (name, field)}
        for label, value in (("Next crop", crop), ("Plant window", window)):
            why = check_text("field %s %s" % (field, label), value)
            if why:
                return {"error": "%s: %s" % (name, why)}
        try:
            datetime.date.fromisoformat(planned_on)
        except ValueError:
            return {"error": "%s: field %s has Planned on %r, not an ISO date"
                             % (name, field, planned_on)}
        if reviewed not in ("yes", "no"):
            return {"error": "%s: field %s has Reviewed %r, not yes or no"
                             % (name, field, reviewed)}
        if int(field) in rows:
            return {"error": "%s names field %s in two rows" % (name, field)}
        rows[int(field)] = {"crop": crop, "window": window,
                            "planned_on": planned_on, "reviewed": reviewed == "yes"}
    return {"rows": rows}


def collect(sanctum_dir):
    """The envelope for `<sanctum>/state/field-plan.md`. See collect_file."""
    return collect_file(plan_path(sanctum_dir))


def collect_file(path):
    """The envelope, always. See the module docstring for the three answers."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        # Short on purpose (it rides on the document and is cut at 160): says it is NOT "nothing
        # planned", and what creates the file.
        return {"error": "No plan file yet (not the same as nothing planned). The next refresh "
                         "creates it, or the first record_field_plan.py --set.", "missing": True}
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError is a ValueError, not an OSError: a stray non-UTF-8 byte (a hand
        # edit in another encoding) used to escape as a traceback and stop the FIELDS publish.
        return {"error": "could not read %s: %s" % (path, exc)}
    parsed = parse(text, os.path.basename(path))
    if "error" in parsed:
        return parsed
    rows = parsed["rows"]
    return {"schema_version": SCHEMA_VERSION, "status": "ok", "plan_file": path,
            "count": len(rows),
            "unreviewed": sorted(f for f, r in rows.items() if not r["reviewed"]),
            "rows": rows}


def main(argv):
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(json.dumps({"error": "usage: read_field_plan.py <sanctum_dir>"}))
        return 1
    result = collect(os.path.abspath(argv[0]))
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
