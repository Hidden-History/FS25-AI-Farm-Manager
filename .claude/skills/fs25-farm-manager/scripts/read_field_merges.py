#!/usr/bin/env python3
"""CONTRACT OPEN-1: the completed/planned field merges, read from the dossiers.

    python3 read_field_merges.py <dossier_dir>

⛔ WHY A SCRIPT AND NOT AN AGENT, and it is the owner's standing rule, not a
preference: "could a script do this deterministically? Then a script does it,
fired automatically -- not an agent, not a turn, not a token." The test is
whether the facts can be extracted deterministically AND whether every extraction
can be independently corroborated. Both hold here, and both are measured -- see
the header of `_parse` for the corroborations and the tests for the controls.

⛔ THE OBJECTION THIS ANSWERS. PLAN-FARM-FIELDS ruling 3 rejected "a Markdown
parser in Lua ... it would break silently on any template change", and the same
objection was raised one layer up against a Python parser over the same prose.
⭐ THE OBJECTION IS ABOUT SILENCE, NOT ABOUT PARSING. This parser cannot break
silently: every drift class returns {"error": ...} and NOTHING ELSE. Measured --
8 of 8 injected format mutations fire, including the exact one the ruling names
(the id list losing its bold markers). A parser that fails loud on a template
change is a different object from one that quietly returns fewer rows.

⛔ AND IT NEVER RETURNS [] OR {} FOR A FAILURE (DEC-001). An empty directory is a
real answer -- "this save has no merges", which every non-Montana save is -- and
it is reported as `status: ok` with `count: 0`. A directory that does not exist,
a dossier that will not parse, or a corroboration that disagrees is an ERROR.
The two must never look alike: emit_fields_xml.py REFUSES to emit on the error
and emits happily on the empty, and collapsing them would ship 122 uncollapsed
rows reporting a 30 ha field as 5.71 ha (RSK-001, guard E1).

⚠ WHAT THIS DOES NOT DECIDE. Whether a merge is DISPLAYED with a marker is the
consumer's rule, not this script's. This reports what the dossiers say --
including `state`, which CONTRACT sec. 3.1's FIELD_MERGES literal cannot carry --
and the consumer chooses. See the `state` note in _parse.

⛔ READ-ONLY. This opens files under the operator's sanctum and writes nothing,
anywhere, ever. The only writes this process performs are to stdout.
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

import glob
import json
import os
import re
import sys

SCHEMA_VERSION = 1

# The dossier's own machine-checkable self-declaration. ⛔ CHECKED FIRST AND
# TREATED AS THE FORMAT CONTRACT: `format_version` and `parity_spec` are what
# make these files a STABLE FORMAT rather than free prose, and a file carrying
# neither is not a dossier this parser has any business reading.
REQUIRED_FRONTMATTER = ("format_version: 1", "parity_spec:")

# The one line every dossier states its merge on.
SIZE_LINE_PREFIX = "**Size / notes:**"

# An ordinary, unmerged field's dossier says so in these words (templates/field-dossier.md).
SINGLE_MARKER = "Single field"


def _parse(path):
    """One dossier -> a merge record, or {"error": ...}. Never a partial row.

    ⭐ THREE INDEPENDENT CORROBORATIONS, AND ALL THREE MUST AGREE. This is what
    makes the extraction safe rather than merely convenient -- each one is
    derived from a DIFFERENT part of the file, so a single rewording cannot
    satisfy all three by accident:

      1. the DECLARED COUNT ("spans 7 savegame field IDs") must equal the length
         of the extracted id list;
      2. the canonical id, taken from the FILENAME, must appear in that list;
      3. the canonical id from the PROSE ("as field #70" / "into one field #110")
         must equal the one from the filename.

    ⛔ ANY DISAGREEMENT IS AN ERROR, NEVER A SKIP AND NEVER A BEST GUESS. A
    dossier we cannot read with certainty is one whose field would be collapsed
    wrongly or not at all, and both are wrong numbers rather than missing ones.
    """
    name = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": "could not read %s: %s" % (name, exc), "file": name}

    for token in REQUIRED_FRONTMATTER:
        if token not in text:
            return {"error": "%s carries no `%s` in its frontmatter, so it does "
                             "not declare the format this parser reads. Refused "
                             "rather than parsed on the assumption that it is one."
                             % (name, token.rstrip(":")), "file": name}

    match = re.match(r"^field-(\d+)\.md$", name)
    if not match:
        return {"error": "%s is not named field-<id>.md, so no canonical id can "
                         "be taken from the filename" % name, "file": name}
    canonical = int(match.group(1))

    line = None
    for candidate in text.split("\n"):
        if candidate.startswith(SIZE_LINE_PREFIX):
            line = candidate
            break
    if line is None:
        return {"error": "%s carries no `%s` line, which is where every dossier "
                         "states its merge" % (name, SIZE_LINE_PREFIX), "file": name}

    # ⛔ STATE IS READ, NOT INFERRED FROM SENTIMENT. CONTRACT sec. 3.2 requires
    # emit_fields_xml.py to tell a COMPLETED merge from a PLANNED one
    # "mechanically rather than by prose sentiment", and this is that mechanism:
    # two mutually exclusive markers, and a line carrying neither -- or both --
    # is an error rather than a default.
    planned = "PLANNED merge" in line
    completed = "Merged field" in line
    # TOLERANT: the words, any case, any dash or none. The line is typed by an agent and a
    # slipped dash must not freeze the FIELDS tab. The MERGE markers stay exact: a drifted
    # merge line has to refuse (reading it as "not merged" emits uncollapsed rows, RSK-001).
    # ANCHORED to the start of the value: a drifted merge line that merely MENTIONS "single field"
    # later in its prose must still refuse, never read as an unmerged field.
    single = re.match(r"\s*single[\s\-\u2013\u2014]*field",
                      line[len(SIZE_LINE_PREFIX):], re.I) is not None
    # ⛔ EXACTLY ONE OF THREE MARKERS. A single (unmerged) field is a VALID dossier and is
    # declared, never inferred from the absence of a merge marker: a merge line that drifted
    # (reworded, case-changed) carries none of the three and must still refuse, because
    # reading it as "not merged" would emit the uncollapsed rows guard E1 exists to stop.
    if planned + completed + single != 1:
        return {"error": "%s's size line declares none of `PLANNED merge`, `Merged field` or "
                         "`%s` (or declares more than one), so its merge state cannot be "
                         "determined. Guessing it would either collapse a merge the player has "
                         "not made, or fail to collapse one he has. FIX, for an ordinary "
                         "unmerged field: make the line start `%s Single field -- not merged.` "
                         "and keep any size or map note after it, or run `record_field_merges.py "
                         "<dossier_dir> --config <sanctum>/config.json --single %d`, which "
                         "writes that line and keeps the old one in the dossier's History. "
                         "For a merged field use `--merge`, never a hand-written line."
                         % (name, SINGLE_MARKER, SIZE_LINE_PREFIX, canonical), "file": name}
    if single:
        return {"file": name, "canonical": canonical, "state": "single",
                "sub_ids": [canonical], "count": 1}
    state = "planned" if planned else "completed"

    counted = re.search(
        r"spans (\d+) savegame field IDs|Currently (\d+) separate savegame field IDs",
        line)
    if not counted:
        return {"error": "%s's size line declares no sub-id COUNT, so the id "
                         "list below it cannot be corroborated" % name, "file": name}
    declared = int(counted.group(1) or counted.group(2))

    sub_ids = None
    for blob in re.findall(r"\*\*([\d,\s]+)\*\*", line):
        candidate_ids = [int(v) for v in re.findall(r"\d+", blob)]
        if len(candidate_ids) > 1:
            sub_ids = candidate_ids
            break
    if sub_ids is None:
        return {"error": "%s's size line carries no bolded multi-id list, so no "
                         "sub-ids can be read" % name, "file": name}

    prose = re.search(r"as field #(\d+)|into one field #(\d+)", line)
    if not prose:
        return {"error": "%s's size line does not name the field its sub-ids "
                         "report as, so the canonical id cannot be corroborated"
                         % name, "file": name}
    canonical_from_prose = int(prose.group(1) or prose.group(2))

    failures = []
    if declared != len(sub_ids):
        failures.append("the line declares %d sub-ids and lists %d"
                        % (declared, len(sub_ids)))
    if canonical not in sub_ids:
        failures.append("the canonical id %d is not in its own sub-id list %s"
                        % (canonical, sub_ids))
    if canonical != canonical_from_prose:
        failures.append("the filename says field %d and the prose says field %d"
                        % (canonical, canonical_from_prose))
    if failures:
        return {"error": "%s does not corroborate itself: %s. Refused rather "
                         "than read, because a merge read wrongly is a wrong "
                         "area, not a missing one."
                         % (name, "; ".join(failures)), "file": name}

    return {"file": name, "canonical": canonical, "state": state,
            "sub_ids": sub_ids, "count": len(sub_ids)}


UNASSESSED_MARKER = "_UNASSESSED.md"


def collect(dossier_dir):
    """Every dossier in the directory. Returns the envelope, always."""
    if not os.path.isdir(dossier_dir):
        return {"error": "no such dossier directory: %s. This is NOT a report "
                         "that the farm has no merged fields -- it is a report "
                         "that we could not ask." % dossier_dir}
    # RSK-031. An EMPTY dossier directory is one our own installer creates, so
    # "no dossiers" is a fact about THIS SANCTUM and not about the SAVEGAME.
    # The marker is what makes those two distinguishable: while it is present
    # nobody has looked, and a zero we did not measure is refused rather than
    # reported. Removing it is the act of saying "I looked."
    if os.path.exists(os.path.join(dossier_dir, UNASSESSED_MARKER)):
        return {"error": "%s still carries %s, the marker written by "
                         "init_sanctum.py: this sanctum has never been assessed "
                         "for merged fields. `count: 0` here would be OUR state "
                         "reported as the SAVEGAME's, which publishes a 30 ha "
                         "field as 5.71 ha. Refused rather than "
                         "measured." % (dossier_dir, UNASSESSED_MARKER)}

    paths = sorted(glob.glob(os.path.join(dossier_dir, "field-*.md")))
    records, errors = [], []
    for path in paths:
        parsed = _parse(path)
        (errors if "error" in parsed else records).append(parsed)

    # ⛔ ONE BAD DOSSIER POISONS THE WHOLE ANSWER, deliberately. A partial merge
    # table is not a smaller correct answer: the fields it failed to read are
    # emitted UNCOLLAPSED, at a fifth of their true area, indistinguishable from
    # fields that were never merged. Refusing everything is the only honest
    # response, and guard E1 requires the emitter to refuse on it.
    if errors:
        return {"error": "%d of %d dossier(s) could not be read with certainty, "
                         "so NO merge table is emitted: a partial one would "
                         "silently under-report every field it missed."
                         % (len(errors), len(paths)),
                "failures": errors}

    # ⛔ A COLLISION IS AN ERROR. One savegame id claimed by two merges means one
    # of them is wrong, and picking either reports a field at the wrong size.
    # A single-field dossier claims no parcel but its own: a field later merged into another
    # leaves its old single dossier behind, and that is not a collision.
    merges_only = [r for r in records if r["state"] != "single"]
    singles = sorted(r["canonical"] for r in records if r["state"] == "single")
    seen = {}
    for record in merges_only:
        for sub in record["sub_ids"]:
            if sub in seen:
                return {"error": "savegame field id %d is claimed by both %s and "
                                 "%s, so no merge table can be trusted"
                                 % (sub, seen[sub], record["file"])}
            seen[sub] = record["file"]

    completed = {r["canonical"]: r["sub_ids"] for r in merges_only
                 if r["state"] == "completed"}
    planned = {r["canonical"]: r["sub_ids"] for r in merges_only
               if r["state"] == "planned"}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        # ⚠ `count: 0` WITH `status: ok` IS A REAL ANSWER and every non-Montana
        # save is exactly that. It is the ONE empty this layer may report as a
        # measurement rather than a failure, because the directory was there and
        # was enumerable.
        "count": len(merges_only),
        "single_field_dossiers": singles,
        "dossier_dir": dossier_dir,
        "dossiers_seen": len(paths),
        # ⛔ COMPLETED ONLY -- CONTRACT sec. 3.2. A planned merge is a merge the
        # player has NOT made; collapsing it would show him a field that does not
        # exist in his game.
        "completed": completed,
        "completed_sub_id_count": sum(len(v) for v in completed.values()),
        # ⚠ CARRIED BUT NOT COLLAPSED, and this is the CONTRACT contradiction's
        # cheap half. sec. 1.2 says each entry carries its state, sec. 3.1's
        # FIELD_MERGES literal has no state field, and sec. 3.2 excludes planned
        # merges from it. Reporting them HERE, separately, resolves that without
        # touching FIELD_MERGES' meaning: a consumer that wants to mark a planned
        # merge has the fact, and one that does not is unaffected.
        "planned": planned,
        "planned_sub_id_count": sum(len(v) for v in planned.values()),
        "identity_fields": ["canonical"],
        "reason": (
            "Read from the per-field dossiers' `%s` lines. Each row is "
            "corroborated three ways -- the declared sub-id count against the "
            "list, the canonical id against its own list, and the filename "
            "against the prose -- and any disagreement refuses the whole table."
            % SIZE_LINE_PREFIX),
    }


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(json.dumps({"error": "usage: read_field_merges.py <dossier_dir>"}))
        return 1
    result = collect(os.path.abspath(sys.argv[1]))
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
