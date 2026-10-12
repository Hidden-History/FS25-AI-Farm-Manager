#!/usr/bin/env python3
"""Publish the FIELDS tab's as-of figures for ONE savegame (CONTRACT sec. 4.2, item C4).

    python3 emit_fields_xml.py <savegame_dir> --mods-dir PATH --dossier-dir PATH
                               [--plan-file PATH] [--farm-id N] [--out PATH] [--profile-dir PATH] [--dry-run]

A sibling of emit_farm_xml.py and emit_productions_xml.py, following them
exactly: the same collect_state.run() subprocess shape, the same atomic write,
the same "a degraded run must not destroy a good document" guard keyed on IDS
rather than a count, and the same in-band JSON summary on stdout.

⛔⛔ GUARD E1 -- IT REFUSES TO EMIT RATHER THAN EMIT UNCOLLAPSED, and this is the
single most important behaviour in the file. Five completed merges span 23
savegame field ids on the owner's save. Emitting one row per savegame id reports
field #45 at 5.71 ha when it is 30.06 ha, and field #70 at 21.96 ha when it is
~105 ha -- a complete, plausible, correctly-ordered list in which five rows are
wrong by up to 6.41x and nothing about it looks wrong. That is RSK-001
exactly. (Worst case measured 2026-09-08 on the owner's save: field #84 is
57.9058 ha and its canonical parcel is 9.0333. #45 alone is the 5.26x case, so
`up to 5.3x` understated the whole set by naming only the field it was found on.)
So `--dossier-dir` is REQUIRED and a merge table that cannot be read with
certainty stops the run: NO document is written and any existing one is left
exactly as it is.

⚠ THE DISTINCTION THAT MAKES THAT WORKABLE. "We asked and this save has no
merges" (an empty dossier directory -- every non-Montana save) is a REAL ANSWER
and emits normally. "We could not ask" (no directory, or a dossier that will not
parse) refuses. read_field_merges.py separates the two; collapsing them would
either wedge every ordinary save or ship the wrong numbers on this one.

⛔ COLLAPSE BY SUM, NEVER BY PICKING THE CANONICAL ROW. `areaHa` is the sum over
subIds. The sub-parcels are disjoint authored polygons (`straddles_farmland:
false` on all 122, measured), so the sum IS the union, not an over-count.
`owned` is the AND over subIds, and disagreement is ABSENT rather than `true`:
a merged field is one worked field, and if any sub-parcel is unowned the player
cannot work all of it.

⛔ PLANNED MERGES ARE NOT COLLAPSED. `#110 <- {110,113,117}` and
`#115 <- {115,119,120}` are merges the player INTENDS, not merges he has made.
Collapsing them would show him a field that does not exist in his game. They
emit as six ordinary rows, and under the approved display that is exactly right:
the `(n)` marker means "this row sums n savegame parcels", derived from #subIds,
so an unmarked row is a TRUE statement rather than an omission.

OUTPUT (schema 1), written atomically beside cards.xml, farm.xml and
productions.xml:
    modSettings/FS25_AIFarmManager25/<savegameKey>/fields.xml
Per-savegame, NEVER the root -- fields are a property of a SAVEGAME (BUG-027).
⛔ PERSISTENT, never consumed on read: a consumed bridge would populate the tab
once and leave it empty forever, indistinguishable from a farm with no fields.
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import quoteattr

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import collect_state  # noqa: E402  -- reuse its subprocess shape
import read_field_plan  # noqa: E402  -- the one parser of the plan store

SCHEMA_VERSION = 1
MOD_NAME = "FS25_AIFarmManager25"
ROOT_TAG = "farmManager25Fields"

# The per-sub-id state the detail panel renders (block 1, d1-d7). Each is a KEY
# in read_fields.py's `field_state` rows and an ATTRIBUTE on our <state> element.
#
# ⛔ d3 (harvest ready) IS ABSENT FROM THIS MAP ON PURPOSE. Its only honest
# source is the membership test growthState in resolved_crop.foliageState[].
# isHarvestReady, which read_fields.py reports as `crop_state` -- and on this
# install `crop_state` is null with its own reason, "growth-state table
# unavailable -- readiness UNKNOWN, not false". So it renders `unknown`.
# ⛔ THE MARKER RULE ground_type in {HARVEST_READY, HARVEST_READY_OTHER} IS
# REFUTED and must not be substituted for it: 12 of 24 positives wrong -- sticky
# after harvest on 10 fields, never fires for 9 crops including POTATO and
# GRASS. It is 122/122 SELF-CONSISTENT, which is exactly why it passed a first
# review: a rule that renders "already harvested" and "ripe" identically is
# fully self-consistent and half wrong.
#
# ⛔ NO ROLLER RUNG AND NO STUBBLE RUNG -- PLAN-FARM-DATA-LAYER sec. 2.2a:376,
# binding. `roller_level` is INVERTED relative to plough and lime and rests on a
# single witness; `stubble_shred_level` is ungrounded. Polarity is NOT uniform
# across these level fields and the inconsistent ones are declared on adjacent
# lines of the same file, so grounding one and generalising to its neighbour
# gets it exactly backwards while looking right in review.
STATE_KEYS = {
    "crop": "fruit_type",        # d1
    "growth": "growth_state",    # d2
    "ground": "ground_type",      # d4
    "weeds": "weed_state",       # d5
    "plow": "plow_level",        # d6  -- 0 = NEEDS PLOUGHING, 1 = ploughed
    "lime": "lime_level",        # d7  -- 0 = NEEDS LIME, 3 = fully limed
}


def _num(value):
    """A finite number, or None. Absence must never become 0."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _run_positional(script, savegame_dir, mods_dir, farm_id):
    """read_farmland_areas.py is the one parser taking a second positional.
    Same shape as collect_state.run() with the extra positional threaded in
    front of the flags -- the call shape that script's own usage line documents.
    """
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script), savegame_dir, mods_dir]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "failed to parse output of %s" % script,
                "stderr": result.stderr[:2000]}


# ---------------------------------------------------------------------------
# PLAN AND NOTES (SPEC-livetest-fixes-2026-10-01 item 3). The mod stays a
# display: every figure the FIELDS detail pane shows for these two lines is
# decided HERE and published, in one of FOUR states a player can tell apart.
#
#   plan   reviewed | unreviewed | none | unknown
#   notes  note     | none       | unknown
#
# ⛔ `none` AND `unknown` ARE DIFFERENT FACTS. `none` = we read the store and
# this field has no plan (or no note): a true statement about the field.
# `unknown` = we could NOT read the store (file missing, corrupt, no dossier
# directory): a statement about OUR reach, never about the field, and it carries
# its reason. Seeded-empty scaffolding (a header-only plan file, a dossier whose
# notes section still says "None yet.") is `none`: it is OUR file saying nothing
# is planned, and it is true of the plan -- it is never read as a measurement of
# the save.
# ---------------------------------------------------------------------------
NOTES_HEADING = "## Notes / quirks"
# What our own scaffolding writes into an unfilled notes section
# (templates/field-dossier.md, record_field_merges.py). Matched on the WHOLE
# section text, so a real note that merely begins with "None" is still a note.
NOTE_SCAFFOLDING = {"none yet.", "none recorded yet.", "none yet", "none"}
MAX_NOTE_CHARS = 300


def _short(reason, limit=160):
    """A reason that rides on the document is bounded: it is read on a game screen."""
    reason = " ".join(str(reason).split())
    return reason if len(reason) <= limit else reason[:limit - 1] + "\u2026"


def plan_for_row(plan, canonical):
    """The plan fact for one canonical field id. `plan` is read_field_plan's
    envelope, or None when the caller supplied no plan file."""
    if plan is None:
        return {"state": "unknown",
                "reason": "this run was not given the plan file, so the plan cannot be shown"}
    if "error" in plan:
        return {"state": "unknown", "reason": _short(plan["error"])}
    row = (plan.get("rows") or {}).get(canonical)
    if row is None:
        return {"state": "none"}
    return {"state": "reviewed" if row["reviewed"] else "unreviewed",
            "crop": row["crop"], "window": row["window"], "planned_on": row["planned_on"]}


def read_note(dossier_dir, canonical):
    """One field's note, from `field-<canonical>.md`'s `## Notes / quirks`.

    ⛔ A MISSING DOSSIER FILE IS `none`, NOT `unknown`: dossiers exist only for
    fields the manager has something durable to say about, and "no dossier" is a
    true answer for most fields. The directory itself is guaranteed readable by
    the merge read that already ran (guard E1). A dossier that EXISTS and cannot be
    read, or has no notes section, is `unknown` with its reason."""
    if not dossier_dir:
        return {"state": "unknown", "reason": "this run was not given a dossier directory"}
    name = "field-%d.md" % canonical
    path = os.path.join(dossier_dir, name)
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().split("\n")
    except FileNotFoundError:
        return {"state": "none"}
    except (OSError, UnicodeDecodeError) as exc:
        return {"state": "unknown", "reason": _short("could not read %s: %s" % (name, exc))}
    starts = [i for i, line in enumerate(lines) if line.strip() == NOTES_HEADING]
    if len(starts) != 1:
        return {"state": "unknown",
                "reason": "%s has %d `%s` sections, not one" % (name, len(starts), NOTES_HEADING)}
    body = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        body.append(line.strip())
    text = " ".join(part for part in body if part)
    text = re.sub(r"^[-*]\s+", "", text)         # the dossier's own leading bullet marker
    # Only OUR unfilled template placeholder is scaffolding; a real note that happens to
    # contain braces is a note.
    if (not text or text.lower() in NOTE_SCAFFOLDING
            or re.fullmatch(r"\{\{ANYTHING_WORTH_REMEMBERING.*\}\}", text)):
        return {"state": "none"}
    truncated = len(text) > MAX_NOTE_CHARS
    return {"state": "note", "text": text[:MAX_NOTE_CHARS], "truncated": truncated}



def read_merges(dossier_dir):
    """The merge table, or a reason. ⛔ NEVER a partial table (guard E1)."""
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "read_field_merges.py"),
           dossier_dir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        out = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, ("read_field_merges.py produced output that is not JSON, so "
                      "this run cannot say whether any field is merged. Refusing "
                      "rather than emitting one row per savegame id: that would "
                      "report a 30 ha field as 5.71 ha. stderr: %s"
                      % result.stderr[:500])
    if "error" in out:
        return None, ("the field merges could not be read with certainty (%s), so "
                      "NO document is written. An uncollapsed list is not a "
                      "smaller correct answer -- it is five wrong areas."
                      % out["error"])
    return out, None


def collect_areas(savegame_dir, mods_dir, farm_id):
    """area_ha and owned per FIELD id, from read_farmland_areas.py.

    ⛔ THIS IS THE OWNERSHIP SOURCE, NOT read_fields.py. read_fields.py emits
    `owned: null` on this save (measured on field 1 and throughout); the
    farmland reader resolves ownership spatially and answers 122/122.
    """
    out = _run_positional("read_farmland_areas.py", savegame_dir, mods_dir, farm_id)
    if not isinstance(out, dict) or "error" in out:
        why = out.get("error") if isinstance(out, dict) else "unusable output"
        return None, "read_farmland_areas.py: %s" % why
    rows = out.get("fields")
    if not isinstance(rows, list):
        return None, "read_farmland_areas.py returned no `fields` list"
    areas = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = row.get("field_id")
        if fid is None:
            continue
        areas[int(fid)] = {"area_ha": _num(row.get("area_ha")),
                           "owned": row.get("owned")}
    return areas, None


def collect_state_rows(savegame_dir, farm_id):
    """Per-field agronomy state, from read_fields.py's `field_state` section."""
    out = collect_state.run("read_fields.py", savegame_dir, farm_id=farm_id)
    if not isinstance(out, dict) or "error" in out:
        why = out.get("error") if isinstance(out, dict) else "unusable output"
        return None, "read_fields.py: %s" % why
    sections = out.get("sections") or {}
    block = sections.get("field_state")
    if not isinstance(block, dict):
        return None, "read_fields.py returned no field_state section"
    if block.get("status") not in ("ok", "unknown_by_design"):
        return None, ("read_fields.py could not read this farm's field state "
                      "(field_state status: %r)" % (block.get("status"),))
    rows = {}
    for row in (block.get("data") or []):
        if isinstance(row, dict) and row.get("id") is not None:
            try:
                rows[int(row["id"])] = row
            except (TypeError, ValueError):
                continue
    return rows, None


def build_rows(areas, states, merges, tally, plan=None, dossier_dir=None):
    """One row per CANONICAL id, ascending. The collapse rule, CONTRACT sec. 3.3."""
    completed = {int(k): [int(v) for v in ids]
                 for k, ids in (merges.get("completed") or {}).items()}

    # subId -> canonical. Any id not in the table is its own canonical.
    canonical_of = {}
    for canonical, subs in completed.items():
        for sub in subs:
            canonical_of[sub] = canonical

    every_id = sorted(set(areas) | set(states) | set(canonical_of))
    grouped = {}
    for fid in every_id:
        grouped.setdefault(canonical_of.get(fid, fid), []).append(fid)

    rows = []
    for canonical in sorted(grouped):
        # ⛔ CANONICAL FIRST, then the rest in save order -- CONTRACT sec. 3.1's
        # own ordering. The reader takes subIds[1] as the row's identity.
        subs = completed.get(canonical) or grouped[canonical]
        subs = [canonical] + [s for s in subs if s != canonical]

        row = {"id": canonical, "name": "Field %d" % canonical, "subIds": subs}
        tally["rows"] += 1
        if len(subs) > 1:
            tally["rows_merged"] += 1

        # ⛔ AREA IS THE SUM OVER subIds, never the canonical id's own area.
        # ⚠ AND IT IS ABSENT IF ANY SUB-ID'S AREA IS: a partial sum UNDER-reports
        # the field, which is a wrong number rather than a missing one -- the
        # trade this project never makes.
        parts = [(areas.get(s) or {}).get("area_ha") for s in subs]
        if parts and all(p is not None for p in parts):
            row["areaHa"] = round(sum(parts), 4)
        else:
            tally["rows_area_unknown"] += 1
            row["areaReason"] = (
                "%d of %d sub-parcel(s) have no resolved polygon area, so the "
                "field's total cannot be summed. A partial sum would under-report "
                "it." % (sum(1 for p in parts if p is None), len(parts)))

        # ⛔ owned IS THE AND OVER subIds, AND `unknown` IS RESERVED FOR
        # UNRESOLVED, NOT FOR DISAGREEMENT.
        #
        # ⚠ THE TWO GOVERNING DOCUMENTS ARE IN TENSION HERE AND THIS RESOLVES IT
        # DELIBERATELY. CONTRACT sec. 3.3 rule 4 says "owned is the AND over
        # subIds, and disagreement is nil, never true"; the build spec's f3 says
        # "AND-ed over subIds", "cannot resolve -> unknown, NEVER false". Read
        # literally the first makes a 2-of-3-owned field `unknown` and the second
        # makes it `false`, and they cannot both hold.
        #
        # ⭐ THE RULE'S OWN STATED PURPOSE decides it: "if any sub-parcel is not
        # owned, the player cannot work all of it, and claiming `true` would be
        # the wrong answer in the DANGEROUS DIRECTION." `false` satisfies that
        # and `unknown` throws away a fact we hold -- we did not fail to ask; we
        # asked and the answer is no. `unknown` means "we could not ask", and
        # spending it on a resolved disagreement is the same over-claim in the
        # other direction.
        #
        # So: every sub-parcel resolved and true -> `true`; every sub-parcel
        # resolved with at least one false -> `false` (the AND); ANY sub-parcel
        # unresolved -> ABSENT, and the reader renders `unknown`.
        # ⛔ A defaulted `false` would tell the player he owns nothing, which is
        # BUG-016's exact shape -- that is why the unresolved branch is absence
        # and not the AND's identity element.
        flags = [(areas.get(s) or {}).get("owned") for s in subs]
        if flags and all(f is True or f is False for f in flags):
            row["owned"] = "true" if all(flags) else "false"
        else:
            tally["rows_owned_unknown"] += 1
            row["ownedReason"] = (
                "ownership could not be resolved for every sub-parcel of this "
                "field, so neither `true` nor `false` is emitted: one would claim "
                "land the player may not be able to work, the other would tell "
                "him he owns nothing.")
        if row.get("owned") == "true":
            tally["rows_owned"] += 1

        # ⛔ PER-SUB-ID STATE, NEVER COLLAPSED HERE. Sub-ids can disagree and on
        # field #45 they do TODAY (45 OAT/7, 46 OAT/7, 36 UNKNOWN/0). The
        # agreeing/differs decision belongs to the reader, which is the half that
        # can render "differs -- 45 OAT * 46 OAT * 36 unknown"; collapsing here
        # would throw the evidence away before anyone could show it. The house
        # rule `one_crop_per_combined_field` is what makes a disagreement worth
        # surfacing rather than averaging: under it, a disagreement MEANS
        # something.
        row["states"] = []
        for sub in subs:
            src = states.get(sub)
            if not isinstance(src, dict):
                continue
            entry = {"sub": sub}
            for attr, key in STATE_KEYS.items():
                value = src.get(key)
                if value is not None and value != "":
                    entry[attr] = str(value)
            row["states"].append(entry)
        if not row["states"]:
            tally["rows_state_absent"] += 1
        # PLAN AND NOTES: one fact each, per CANONICAL id (a merged field is one
        # plan row and one dossier). See plan_for_row / read_note for the four states.
        row["plan"] = plan_for_row(plan, canonical)
        row["notes"] = read_note(dossier_dir, canonical)
        for key, fact in (("plan", row["plan"]), ("notes", row["notes"])):
            name = "rows_%s_%s" % (key, fact["state"])
            tally[name] = tally.get(name, 0) + 1
        rows.append(row)
    return rows


def build_xml(rows, savegame_key, generated_at, farm_id, dropped=()):
    """⛔ AN ATTRIBUTE THAT CANNOT BE RESOLVED IS ABSENT, never `0` and never "".
    `subIds` is omitted for a single field -- omission is not absence of data,
    `subIds = {id}` is the reader's default and its array is total either way.

    `dropped` is the ids this run removes from what was already published. It
    rides on the DOCUMENT and not only on stdout because stdout is gone the
    moment the run ends, and a tab that quietly loses four fields with no
    surviving record of it is exactly DEC-001's shape. Empty -> absent, like
    every other unresolved attribute here.
    """
    def attrs(pairs):
        return "".join(" %s=%s" % (k, quoteattr(str(v)))
                       for k, v in pairs if v is not None)

    body = []
    for row in rows:
        subs = row["subIds"]
        body.append("\n  <field%s" % attrs([
            ("id", row["id"]), ("name", row["name"]),
            ("areaHa", row.get("areaHa")), ("owned", row.get("owned")),
            ("subIds", " ".join(str(s) for s in subs) if len(subs) > 1 else None),
            ("areaReason", row.get("areaReason")),
            ("ownedReason", row.get("ownedReason")),
        ]))
        has_plan, has_notes = row.get("plan"), row.get("notes")
        if not row["states"] and not has_plan and not has_notes:
            body.append("/>")
            continue
        body.append(">")
        for entry in row["states"]:
            body.append("\n    <state%s/>" % attrs(
                [("sub", entry["sub"])]
                + [(k, entry.get(k)) for k in sorted(STATE_KEYS)]))
        # ⛔ ALWAYS EMITTED WHEN KNOWN TO THE BUILDER, even for `none`: an absent
        # element is what an OLD emitter's document looks like, and the reader
        # must be able to tell "this build said none" from "this build never said".
        if has_plan:
            body.append("\n    <plan%s/>" % attrs([
                ("state", has_plan["state"]), ("crop", has_plan.get("crop")),
                ("window", has_plan.get("window")),
                ("plannedOn", has_plan.get("planned_on")),
                ("reason", has_plan.get("reason"))]))
        if has_notes:
            body.append("\n    <notes%s/>" % attrs([
                ("state", has_notes["state"]), ("text", has_notes.get("text")),
                ("truncated", "true" if has_notes.get("truncated") else None),
                ("reason", has_notes.get("reason"))]))
        body.append("\n  </field>")

    root_extra = ""
    if dropped:
        root_extra = attrs([
            ("droppedIds", " ".join(str(d) for d in dropped)),
            ("droppedReason", "published previously and absent from this run; "
                              "republished without them rather than freezing "
                              "the tab, and recorded here so the drop is not "
                              "silent"),
        ])

    return (
        '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        '<%s schema=%s generatedAt=%s savegame=%s farmId=%s%s>%s\n'
        '</%s>\n'
    ) % (ROOT_TAG, quoteattr(str(SCHEMA_VERSION)), quoteattr(generated_at),
         quoteattr(savegame_key), quoteattr(str(farm_id)), root_extra,
         "".join(body), ROOT_TAG)


def published_fields(path):
    """Which <field> ids the document already on disk publishes, and whether it
    could be READ at all. ⛔ THE IDS, NOT A COUNT -- emit_farm_xml.py's guard.

    ⛔ `readable` IS A CLAIM ABOUT OUR KNOWLEDGE, NOT ABOUT THE FILE. It is True
    only when the id set returned is a REAL ANSWER: no file at all (which
    publishes nothing, and we know it), or a document we actually parsed. A parse
    failure returns False because we did not learn what it publishes, and saying
    otherwise would let a degraded run overwrite a corrupt document while the
    caller believed it had checked.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            root = ET.parse(handle).getroot()
    except FileNotFoundError:
        return set(), True
    except ET.ParseError:
        # ⛔ F3, 2026-09-08: THE CODE WAS FIXED, NOT THE PROSE. This mapped to
        # `True` -- "readable, publishes nothing" -- which is the one thing we
        # do NOT know about a document we could not parse. `True` here makes
        # "we could not look" and "we looked and it is empty" the SAME VALUE,
        # which is DEC-001's founding defect at the guard that exists to
        # prevent it: prior_ids is empty either way, so `lost` is empty, so
        # every drop guard silently cannot fire over a corrupt document.
        # FileNotFoundError stays True because that IS a real answer -- no
        # file publishes nothing, and we know it.
        return set(), False
    except OSError:
        return set(), False
    if root.tag != ROOT_TAG:
        return set(), True
    return {f.get("id") for f in root.findall("field") if f.get("id")}, True


def published_merge_shape(path):
    """{id: (subIds...)} for the document already on disk -- THE ANSWER, not the
    id set. ⛔ A LOSS TEST CANNOT SEE RSK-031: uncollapsing 5 merged rows turned
    104 rows into 122, a strict SUPERSET, so no id was lost and the document grew
    while getting worse. Total area cannot see it either -- the collapse is a sum
    over a partition, so the hectare total is conserved EXACTLY (measured:
    1037.0121 both ways). Only the per-field shape moves.

    ⚠ THIS STILL COLLAPSES ParseError INTO `{}` -- the same "could not read" /
    "read it, no merges" ambiguity that F3 repaired in published_fields above,
    left in place deliberately rather than widened into that fix's scope. The
    consequence, measured 2026-09-08 and stated at its true scope: over a CORRUPT
    document `prior_shape` is empty, so the demerge guard cannot fire, and
    because `hard_notes` is `[]` on every path through main() today, branch 2
    cannot catch the run either. EVERY run through main() over a corrupt document
    bypasses the RSK-031 guard, clean or degraded -- not merely a clean one. That
    write is the repair we want and it is not judged a live risk, but F3 is
    therefore a correctness fix to the unit and a PRECONDITION for future work,
    not live protection today."""
    try:
        with open(path, encoding="utf-8") as handle:
            root = ET.parse(handle).getroot()
    except (FileNotFoundError, ET.ParseError, OSError):
        return {}
    if root.tag != ROOT_TAG:
        return {}
    shape = {}
    for field in root.findall("field"):
        fid = field.get("id")
        if fid:
            shape[fid] = tuple((field.get("subIds") or fid).split())
    return shape


def decide_publication(out, rows, hard_notes):
    """May this run overwrite the document already at `out`, and which published
    ids does it drop if it does?  Returns (refused_reason_or_None, dropped_ids).

    ⛔⛔ EXTRACTED SO THE DECISION IS REACHABLE BY A TEST. While this lived inline
    in main() it could only be driven through a real savegame and a real map mod,
    and one of its branches was consequently DEAD IN SHIPPED CODE: `lost` was
    computed and then read only as `notes and lost`, so on a CLEAN run
    (notes == []) both notes-gated branches short-circuited and the drop was
    never evaluated at all. Green because control never arrived, not because the
    case was handled. Asked "which test drives `lost` truthy with `notes: []`
    into that branch?", the honest answer was NONE. This function is what makes
    that answer stop being true.

    ⛔ THE ORDER IS THE POLICY. Each branch answers a different question:

      1. `demerged` -- did a field published as MERGED lose any of the
         sub-parcels it was published with? That is a wrong AREA, not a missing
         row, and no loss test can ever see it: uncollapsing 5 merges turned 104
         rows into 122, a strict SUPERSET, so nothing was lost while field 45
         went from 30.06 ha to 5.71. Answer-keyed, and deliberately NOT gated on
         notes, because the incident ran with notes == [] (RSK-031).
         ⛔ F1, 2026-09-08: THIS COMPARES SUB-PARCEL IDENTITY, NOT COUNT. It read
         `len(new_shape.get(fid, ())) < len(subs)`, so an EQUAL-CARDINALITY swap
         walked straight through the guard built to stop it: field 45 published
         as (45,46,36) and republished as (45,99,100) WROTE, and areaHa went
         30.0626 -> 5.7127 -- the RSK-031 wrong answer reaching disk THROUGH the
         guard. The test is SUBSET, not inequality: every sub-parcel we already
         published must still be there. Inequality would also refuse
         (45,46,36) -> (45,46,36,50), a legitimate FURTHER merge, and refuse it
         again every run -- freezing the tab on the very workflow the guard
         exists to protect.
      2. A HARD-degraded run over a document we could not READ -- we cannot see
         what we would destroy, so we destroy nothing.
      3. A HARD-degraded run that DROPS ids -- a run already known to have gone
         wrong does not get to shrink the published list.
         ⛔ F2, 2026-09-08 (owner ruling): BRANCHES 2 AND 3 TAKE `hard_notes`,
         NOT EVERY NOTE. They read `notes`, and `notes` is not a severity: this
         file documents the collect_state_rows failure in main() as "⚠ DEGRADED,
         NOT FATAL ... still worth publishing". So a tolerated soft degradation
         plus a legitimate land sale REFUSED, and refused again every run while
         that soft condition persisted -- freezing the tab on stale data, which
         is the exact failure branch 4's ruling exists to prevent. Measured
         2026-09-08 by driving main(): of its four note sites, three leave
         `rows is None` and never reach publish() at all, so the SOFT note was
         not an edge case of these branches -- it was the ONLY one that could
         reach them. Severity is declared by the site that emits the note; it is
         never inferred from the note's text.
         ⛔⛔ AND SO BRANCHES 2 AND 3 ARE DEAD CODE IN THE SHIPPING PATH TODAY.
         Measured 2026-09-08 by spying the real publish() call: `hard_notes` is
         `[]` on EVERY path through main(), because every hard-note site leaves
         `rows is None` and main() refuses earlier. These two branches read as
         live protection and are not: nothing a player can do reaches them. If
         you wire a hard note that coexists with rows, you are ACTIVATING A
         DECISION THAT HAS NEVER BEEN LIVE-TESTED -- the unit tests below are the
         only thing that has ever exercised it.
      4. ⭐ A CLEAN run that drops ids -- THIS WRITES, and that is the ruling of
         2026-09-08, re-ruled as D-11 (DEC-222, 2026-09-23): publish and
         DISCLOSE. ⚠ The 09-08 reason ("the player SELLS LAND") was wrong -- a
         sale only flips `owned` and can never drop a row (F11); a dropped id
         means the map read lost one. Refusing here would still freeze the whole
         tab: every subsequent run would see the same missing ids and refuse for
         the same reason, so the tab would silently stop tracking his farm. That is a worse failure than the one
         being prevented. But writing it away in silence is DEC-001's founding
         defect. "Write, and say which ids went" is the only third answer, so
         the ids come back to the caller for `notes` and for the document.
    """
    prior_ids, prior_readable = published_fields(out)
    prior_shape = published_merge_shape(out)
    new_shape = {str(r["id"]): tuple(str(s) for s in
                                     (r.get("subIds") or [r["id"]]))
                 for r in rows}
    # ⛔ F11(3) / BUG-049 (U9). Compare EVERY published id -- top-level rows AND
    # the sub-parcels merged into them -- on both sides. Top-level ids alone
    # made every parcel absorbed into a newly recorded merge look lost, and
    # published a false "land the player SOLD" note that marked a healthy
    # publish degraded (exit 1).
    prior_all = set(prior_ids) | {s for subs in prior_shape.values() for s in subs}
    new_all = set(new_shape) | {s for subs in new_shape.values() for s in subs}
    lost = sorted(prior_all - new_all)
    demerged = sorted(
        fid for fid, subs in prior_shape.items()
        if len(subs) > 1 and not set(subs) <= set(new_shape.get(fid, ())))

    if demerged:
        return ("field(s) %s are published at %s as merged and this "
                "run would republish them with FEWER sub-parcels, so "
                "a worked field would revert to one of its parts and "
                "report a fraction of its true area. The existing "
                "document is kept untouched. No id is lost by this "
                "change, which is exactly why a loss test cannot see "
                "it. To resolve: if the dossier is wrong, "
                "correct it; if the dossier is right (the merge really "
                "is smaller now), move %s aside -- it is the manager's "
                "own published file, not the save -- and refresh, and "
                "the tab republishes from the dossiers."
                % (", ".join(demerged), out, out)), ()
    if hard_notes and not prior_readable:
        return ("degraded run, and the document already at %s could not "
                "be read to see what it publishes; it is kept untouched "
                "rather than overwritten on the assumption that it holds "
                "nothing" % out), ()
    if hard_notes and lost:
        return ("degraded run would have dropped published field(s) %s; "
                "the existing document is kept and its generatedAt left "
                "alone" % ", ".join(lost)), ()
    return None, tuple(lost)


def publish(out, rows, notes, savegame_key, generated_at, farm_id,
            hard_notes=None):
    """The entire publication step, and THE ONLY PATH main() takes to disk.

    ⛔ IT IS ONE FUNCTION ON PURPOSE. A test that re-assembled decide ->
    note -> build -> write in its own body would be asserting its own copy of
    the sequence, and would stay green if main() ever stopped following it.
    Driving THIS is driving what actually ships.

    `hard_notes` is the subset of `notes` whose emitting site declared the run
    UNTRUSTWORTHY, and it is what the refusal branches read. Omitted, it defaults
    to a COPY of `notes` -- every note treated as hard -- because that is this
    function's behaviour before F2 and the more restrictive of the two answers: a
    caller that says nothing about severity gets the refusal, never the write.
    ⛔ main() PASSES IT EXPLICITLY. If that wiring is ever dropped the F2 fix
    goes inert while every test that constructs its own notes list still passes,
    so a test drives main() itself rather than only this function.

    Returns (written_path_or_None, refused_reason_or_None).
    """
    if hard_notes is None:
        # A copy rather than an alias. ⚠ INERT TODAY, AND SAY SO: the append
        # below happens AFTER the decision, so aliasing changes no outcome and
        # NO TEST CAN REDDEN FOR THIS LINE ALONE -- measured 2026-09-08, the
        # copy->alias mutation leaves the whole suite green. It is not decoration
        # either. Add the re-decide this comment guards against and the pair
        # separates cleanly: re-decide + copy stays GREEN, re-decide + alias goes
        # RED on four tests with the self-fulfilling note reproduced verbatim
        # ("a legitimate land sale froze the tab"). So: worth keeping, worth
        # nobody believing it is what stops the note. The ORDERING is that.
        hard_notes = list(notes)
    refused, dropped = decide_publication(out, rows, hard_notes)
    if dropped:
        # ⛔ APPENDED AFTER THE DECISION, NEVER BEFORE IT. `hard_notes` is an
        # INPUT to decide_publication -- appending this first would make a clean
        # run look degraded, take the `hard_notes and lost` branch and refuse, so
        # the note recording the drop would itself cause the refusal it
        # describes. A self-fulfilling note.
        # ⛔ THE ORDERING IS THE WHOLE DEFENCE, AND IT IS THE ONLY ONE. An
        # earlier version of this comment claimed a second, independent reason --
        # that `hard_notes` is a different list object. THAT IS NOT A DEFENCE and
        # the claim was wrong: decide_publication reads the note VALUES, not the
        # list's identity, so a copy protects nothing. Measured 2026-09-08: reuse
        # one `notes` list across two publish() calls and run 1's drop note is
        # COPIED INTO run 2's hard_notes and causes the very refusal it describes
        # -- the self-fulfilling note, reproduced through the copy. Not live:
        # main() calls publish() once with a fresh list. If you ever call it
        # twice with the same list, filter the drop note out yourself.
        # ⛔ F11 / D-11 (DEC-222): publish and DISCLOSE. A sale can never
        # populate `dropped` -- rows cover every map field and a sale only
        # flips `owned` -- so the old "land the player SOLD" cause was false.
        # This is a SOFT note: never add it to hard_notes (the blocking branch).
        notes.append(
            "field id(s) %s are no longer in this run's map read (a map or mod "
            "change, or a read failure); republished without them. The ids are "
            "recorded here and on the document's droppedIds attribute: a drop "
            "is allowed, a SILENT drop is not." % ", ".join(dropped))
    if refused is not None:
        return None, refused
    atomic_write(out, build_xml(rows, savegame_key, generated_at, farm_id,
                                dropped=dropped))
    return out, None


def atomic_write(path, text):
    """Write-then-rename. A reader must never catch a half-written document and
    conclude the farm has no fields."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=directory, prefix=".fields-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def add_note(notes, hard_notes, why, hard=True):
    """Record one note, and whether it is HARD.

    ⛔ SEVERITY IS DECLARED BY THE SITE THAT EMITS THE NOTE, never matched out of
    the note's text later. A classifier keyed on wording is a gate keyed on
    prose: it stops checking rather than failing the day someone rewords a
    message, and nothing goes red. The default is `hard` because the restrictive
    answer is the safe one to forget.

    HARD  -- the run is untrustworthy; it does not get to shrink or overwrite
             what is already published.
    SOFT  -- a tolerated degradation. The rows are still true, so the run still
             publishes (F2, owner ruling 2026-09-08).
    """
    notes.append(why)
    if hard:
        hard_notes.append(why)


def main():
    parser = argparse.ArgumentParser(description="Emit the FIELDS tab's as-of values.")
    parser.add_argument("savegame_dir")
    parser.add_argument("--farm-id", type=int, default=1)
    parser.add_argument("--mods-dir", default=None,
                        help="needed by read_farmland_areas.py to resolve the map")
    parser.add_argument("--dossier-dir", default=None,
                        help="sanctum/state/field-dossiers -- REQUIRED (guard E1)")
    parser.add_argument("--plan-file", default=None,
                        help="sanctum/state/field-plan.md -- the per-field crop plan the "
                             "detail pane shows. Omitted: every row publishes plan `unknown`")
    parser.add_argument("--out", default=None)
    parser.add_argument("--profile-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    savegame_dir = os.path.abspath(args.savegame_dir)
    if not os.path.isdir(savegame_dir):
        print(json.dumps({"error": "no such savegame_dir: %s" % savegame_dir}))
        return 1
    savegame_key = os.path.basename(savegame_dir.rstrip("/\\"))

    if not args.mods_dir:
        print(json.dumps({"error": "--mods-dir is required: read_farmland_areas.py "
                                   "resolves the map through it, and without it no "
                                   "field area or ownership can be resolved at all"}))
        return 1
    # ⛔ GUARD E1, ENFORCED AT THE ARGUMENT. A caller who says nothing about
    # merges has not told us there are none -- and defaulting to "none" is the
    # uncollapsed emit this whole file exists to refuse.
    if not args.dossier_dir:
        print(json.dumps({"error": "--dossier-dir is required. Without it this run "
                                   "cannot tell a save with no merged fields from "
                                   "one whose merges it failed to read, and the "
                                   "second emits five fields at up to a fifth of "
                                   "their true area (guard E1)."}))
        return 1

    tally = {"rows": 0, "rows_merged": 0, "rows_owned": 0,
             "rows_area_unknown": 0, "rows_owned_unknown": 0,
             "rows_state_absent": 0}
    notes, hard_notes, rows, merges, plan = [], [], None, None, None
    try:
        merges, why = read_merges(os.path.abspath(args.dossier_dir))
        if why:
            add_note(notes, hard_notes, why)
        else:
            areas, why = collect_areas(savegame_dir, args.mods_dir, args.farm_id)
            if why:
                add_note(notes, hard_notes, why)
            else:
                states, why = collect_state_rows(savegame_dir, args.farm_id)
                if why:
                    # ⚠ DEGRADED, NOT FATAL. Without field_state the detail panel
                    # reads `unknown` -- but name, area and ownership are still
                    # true and still worth publishing.
                    # ⛔ THE ONLY SOFT NOTE IN THIS FUNCTION, and the only note
                    # site that reaches publish() at all: measured 2026-09-08 by
                    # driving main(), the other three leave `rows is None`, so
                    # main() refuses with "nothing was collected" before publish()
                    # is called. Marking it soft is what stops a degradation this
                    # comment calls NOT FATAL from freezing the tab on a land sale.
                    add_note(notes, hard_notes, why, hard=False)
                    states = {}
                # THE PLAN STORE. ⛔ A MISSING FILE IS NOT A NOTE: an older sanctum has
                # none, and `unknown` rides in the document itself with its reason. A
                # file that is THERE and unreadable is a real defect: a soft note
                # (the rows are still true), so the refresh reports it degraded.
                plan = None
                if args.plan_file:
                    plan = read_field_plan.collect_file(os.path.abspath(args.plan_file))
                    if "error" in plan and not plan.get("missing"):
                        add_note(notes, hard_notes, "the field plan could not be read, so "
                                 "every field shows its plan as unknown: %s" % plan["error"],
                                 hard=False)
                # Positional on purpose: tests/test_rsk031_unassessed_dossiers.py replaces
                # build_rows with a `*a` stub to force one failure site through main().
                rows = build_rows(areas, states, merges, tally, plan,
                                  os.path.abspath(args.dossier_dir))
                for row in rows:
                    fact = row.get("notes") or {}
                    if fact.get("state") == "unknown":
                        add_note(notes, hard_notes, "field %d's note could not be read: %s"
                                 % (row["id"], fact.get("reason")), hard=False)
    except Exception as exc:                            # a parser crash is a note
        add_note(notes, hard_notes, "%s: %s" % (type(exc).__name__, exc))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = args.out
    if out is None:
        profile = args.profile_dir or os.path.dirname(savegame_dir)
        out = os.path.join(profile, "modSettings", MOD_NAME, savegame_key,
                           "fields.xml")

    written = refused = None
    if rows is None:
        # ⛔ NOTHING IS WRITTEN. An empty document carrying a fresh generatedAt is
        # absence overwriting presence, and the atomicity of the write would make
        # it worse rather than better: the replacement would be clean and complete.
        refused = ("nothing was collected, so no document is written and any "
                   "existing one is left exactly as it is")
    else:
        if args.dry_run:
            print(build_xml(rows, savegame_key, generated_at, args.farm_id))
        else:
            written, refused = publish(out, rows, notes, savegame_key,
                                       generated_at, args.farm_id,
                                       hard_notes=hard_notes)

    print(json.dumps({
        "written": written,
        "refused": refused,
        "savegame": savegame_key,
        "farm_id": args.farm_id,
        "generated_at": generated_at,
        "merges_completed": len((merges or {}).get("completed") or {}),
        "merges_planned": len((merges or {}).get("planned") or {}),
        "merge_sub_ids_collapsed": (merges or {}).get("completed_sub_id_count"),
        "plan": ({"status": "not_given"} if plan is None else
                 {"status": "missing" if plan.get("missing") else
                  ("error" if "error" in plan else "ok"),
                  "rows": plan.get("count"), "unreviewed": plan.get("unreviewed")}),
        "tally": tally,
        "notes": notes,
    }, indent=2))
    return 1 if notes or rows is None else 0


if __name__ == "__main__":
    sys.exit(main())
