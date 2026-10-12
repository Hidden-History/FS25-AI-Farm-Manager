#!/usr/bin/env python3
"""Publish the PRODUCTIONS tab's as-of figures for ONE savegame (SPEC Block D, D1).

    python3 emit_productions_xml.py <savegame_dir> [--farm-id N] [--cache-dir PATH]
                                    [--out PATH] [--profile-dir PATH] [--dry-run]

WHAT THIS IS
------------
A sibling of emit_farm_xml.py, following it exactly: same collect_state.run()
subprocess shape, same atomic write, same "a degraded run must not destroy a
good document" guard, same in-band JSON summary on stdout.

⛔ EVERY FIGURE ON THIS TAB IS FILE / AS-OF. There is no live half, so the
document carries TWO stamps and the tab renders both:
    generatedAt -- when THIS run read the savegame
    defsAsOf    -- when the production_defs cache was generated
They can differ by weeks. Reporting one would let definition data weeks old
borrow the freshness of a savegame read seconds ago.

⭐ IT COMPOSES AN EXISTING DERIVATION; IT DOES NOT REIMPLEMENT ONE.
read_state.derive_production_demand() already joins production_lines,
storage_fill_levels, production_recipes and greenhouse_recipes and already
handles four failure modes the obvious implementation gets wrong (greenhouse
recipes in a sibling section, pass-through fill types, pass-through candidates
contaminating a rate average, and stock shared between lines). Burn rates,
runways and the shared-stock index are READ from it, never recomputed here.

⛔ WHAT THIS FILE DOES ADD, and why it is not a second derivation. The demand
section answers "what does this line BURN". The tab also needs "what does this
line PRODUCE" (l3) and "how big is the output tank" (o3), and neither is in it.
Both are computed here under the SAME refusal rule the demand join uses --
agreement is judged on the COMPUTED ANSWER, and candidates that disagree emit
no number at all. See _agree().

⛔ THE SPLIT THAT KEEPS IT CHEAP (SPEC 6.2.2):
    read_productions.py         -- RE-RUN. It reads one savegame file and costs
                                   ~0.7 s measured; the cache's copy predates
                                   `production_points` entirely.
    cache/domains/production_defs.json -- READ FROM CACHE. Definition data
                                   cannot change during play, and regenerating
                                   it costs a 900-second install-tree walk.
⚠ THE FALSIFIER, stated because it is the one thing that could sink that trade:
if the owner installs or removes a mod without regenerating the cache, every
defs-derived figure is silently from the old install. Mitigated -- NOT
eliminated -- by writing defsAsOf onto the document and rendering it.

⛔ WHAT CANNOT BE RESOLVED RENDERS `unknown`, AND IT IS NEVER A NUMBER.
An attribute that cannot be resolved is ABSENT from the document -- never 0,
never "". A blank and a zero are both absence dressed as data. `0.0` hours of
runway is a REAL measured value meaning "starved right now", and it is the most
important state on the tab, so it must stay distinguishable from "we could not
ask" all the way to the pixel.

⚠ BUT A MISSING STORAGE NODE IS NOT ONE OF THOSE THINGS -- see TECH-DEBT-139
below. The game OMITS an empty production node rather than writing
`fillLevel="0.000000"`, so "no node" is how the savegame SAYS zero. Reporting it
as `unknown` was this rule inverted: data rendered as absence. An absent node
now earns a verdict -- `empty` (a measured 0, flagged) or `notStarted` (a chain
never supplied, excluded from urgency) -- and `unknown` is kept for what is
genuinely undecidable, so the word keeps its meaning. `stockState` carries the
verdict; the full rule, its measured premise and its three fail-closed guards
are at classify_absent_stock().

OUTPUT (schema 1), written atomically beside cards.xml and farm.xml:
    modSettings/FS25_AIFarmManager25/<savegameKey>/productions.xml
Per-savegame, NEVER the root: productions are a property of a SAVEGAME
(BUG-027), and FarmManager25.lua refuses an unscoped store.
⛔ PERSISTENT, never consumed on read -- a consumed bridge would populate the
tab once and leave it empty forever, indistinguishable from the legitimate
no-productions state.
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import quoteattr

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import cache_provenance as provenance   # noqa: E402
import collect_state                    # noqa: E402  -- reuse its subprocess shape
import read_state                       # noqa: E402  -- reuse the derivation, do not reimplement it
import read_building_capacity           # noqa: E402  -- item 9: the per-building ceiling join

SCHEMA_VERSION = 1
MOD_NAME = "FS25_AIFarmManager25"
ROOT_TAG = "farmManager25Productions"

# The two domains this document is derived from. Named once so a reader can see
# the whole dependency without reading the body.
DOMAIN_SAVEGAME = "productions"
DOMAIN_DEFS = "production_defs"


# ---------------------------------------------------------------------------
# V-20 -- THE FRESHNESS VERDICT FOR A FRESHLY RE-RUN DOMAIN.
#
# ⛔ THE GAP, AND WHY A DEFAULT WOULD HAVE BEEN THE WRONG FIX.
# derive_production_demand() REQUIRES domain_status / domain_checks /
# accepted_stale and gives them no default, so that no caller can call every
# source `verified_current` on no evidence at all. Those verdicts come from
# read_state.verify_domain(), whose FIRST act is
# `entry = record.get("cache_entry") or {}`.
#
# A freshly re-run parser emits NO `cache_entry` -- it carries
# schema_version / domain / set / farm_id / capability_ids / provenance /
# status / reason / sections, and nothing else; `cache_entry` is added by
# generate_state.py at CACHE time. So this file's hybrid `records` -- a fresh
# `productions` half beside a cached `production_defs` half -- holds one domain
# verify_domain was never written for.
#
# ⛔ THE FIX IS NOT A DEFAULT AND NOT A SPECIAL CASE FOR "FRESH". Passing
# ("ok", full, performed) because we just ran the parser would assert a
# comparison nobody performed, which is the exact false affirmation
# _render_source_domain and _source_domain_status were both written to prevent.
#
# ⭐ THE ANSWER IS TO ACTUALLY VERIFY IT, and the evidence is already in hand.
# read_productions.py declares its own sources with sha256 digests and a
# source_set_hash in `provenance` (measured: placeables.xml, one source). So
# this re-reads and re-hashes those files and compares -- the SAME check
# verify_domain performs, through the SAME cache_provenance functions, minus
# only the cache_entry lookup that has nothing to look up. The verdict is
# earned, not assumed.
#
# ⚠ AND IT IS NOT VACUOUS. The window between the parser's read and this check
# is small but real, and the player saving the game inside it is exactly what
# would change placeables.xml underneath us. A verdict that could never be
# "stale" would be a default wearing a check's clothes.
#
# ⛔ IT FAILS CLOSED. A parser envelope with no provenance, an empty sources
# list or no source_set_hash yields "stale" -- never "ok" -- because
# extract_source_set treats absence as an error rather than as nothing to
# verify. Downstream, _demand_envelope then downgrades the section's status and
# stamps the reason, so a document derived from an unverifiable read says so.
# ---------------------------------------------------------------------------
def verify_fresh_envelope(envelope, mode=provenance.FULL):
    """Verify a JUST-RUN parser envelope against the sources it declares.

    Returns (status, reason, detail) in verify_domain()'s own shape, so the two
    verdicts can be put side by side in one `domain_status` map without a
    consumer having to know which came from where.
    """
    sources, recorded, err = provenance.extract_source_set(envelope)
    if err:
        return "stale", (
            "this freshly-run domain's provenance cannot be used to verify it: %s"
            % err), {"comparison": read_state.NOT_PERFORMED}
    verdict, reason, detail = provenance.verify_source_set(sources, recorded, mode=mode)
    detail = dict(detail, comparison=read_state.PERFORMED)
    if verdict == provenance.CURRENT:
        return "ok", None, detail
    return "stale", reason, detail


def _num(v):
    """A finite number, or None. Absence must never become 0.

    Coerces numeric STRINGS: read_production_defs.py emits `cycles_per_hour`
    and input/output `amount` as the raw uncoerced strings they are in the XML
    ("160"), and an earlier draft of emit_farm_xml.py that accepted only
    int/float silently dropped every figure -- "absent" and "arrived as a
    string" looked identical downstream.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            return None
    if not isinstance(v, (int, float)):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def _round(v, places=2):
    return None if v is None else round(v, places)


def _agree(values):
    """(the one agreed value, None) or (None, the distinct values) -- BUG-026's
    rule, applied to any figure resolved through more than one definition.

    ⛔ AGREEMENT IS JUDGED ON THE COMPUTED ANSWER, never on the text that
    produced it. Two definitions that differ in wording but yield the same
    number are not an ambiguity, and calling them one would bury real answers in
    noise. Two that yield different numbers are an ambiguity NO tie-break may
    resolve: `production_id` does not identify one recipe, nothing in the
    savegame layer says which definition a placeable uses, and picking one ships
    a plausible number wrong by the full spread. Measured on the live cache:
    `furniturePlanks`/PLANKS resolves to 5 definitions at {14.0, 140.0} L/h.
    """
    distinct = sorted({v for v in values if v is not None})
    if not distinct:
        return None, []
    if len(distinct) > 1:
        return None, distinct
    return distinct[0], []


_HEX_CHARS = set("0123456789abcdefABCDEF")


def _is_hex_blob(s, min_len=16):
    return len(s) >= min_len and all(c in _HEX_CHARS for c in s)


def _title_from_id(placeable_id):
    """`preplaced_carpenterUS_7ed62c...` -> `Carpenter US`. PRESENTATION ONLY.

    ⚠ 7 of 46 line rows carry `placeable_name: "<unnamed>"` on the live save
    (measured), and a point with no name renders as a blank row the player
    cannot click with intent. This derives a label from the id the way
    read_state._derived_label already does for line names -- and the document
    MARKS it `nameSource="derived"` so a derived label is never mistaken for
    the one the game authored.

    ⛔⛔ DEC-212 BACKSTOP -- NO PATH MAY EVER PRINT A HEX ID. Player-built
    placeables carry ids shaped `placeable<32 hex>`, with NO underscore, so
    neither the prefix strip nor the trailing-hex-blob strip below ever fires
    on them, and title-casing the id verbatim produces gibberish that LOOKS
    like a name (measured: `Placeable90Af1530660Af6De50D79E98A52A9A64`). The
    real fix is build_points() deriving from the placeable's FILE name
    instead (DEC-212); this is the fallback of last resort for whatever
    reaches this function with no filename to derive from.
    """
    stem = str(placeable_id or "")
    for prefix in ("preplaced_", "placeable_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    else:
        # The bare "placeable" prefix (no "_") is stripped ONLY when what is
        # left is itself a hex blob, so a genuine word starting with
        # "placeable" is never mistaken for this shape.
        if stem.startswith("placeable") and _is_hex_blob(stem[len("placeable"):]):
            stem = stem[len("placeable"):]
    # Trailing hex blob: the savegame's own uniqueness suffix, never a name.
    parts = stem.split("_")
    if len(parts) > 1 and _is_hex_blob(parts[-1]):
        parts = parts[:-1]
    stem = "_".join(parts)
    if _is_hex_blob(stem):
        return "Placeable"
    return read_state._spaced(stem) if stem else ""


def _title_from_filename(filename):
    """`.../greenHouseMushroomsLarge.xml` -> `Green House Mushrooms Large`.

    DEC-212's primary fallback for a failed resolution: a spaced label from
    the placeable's own FILE name, `.xml` stripped, PRESENTATION ONLY --
    same idiom as _title_from_id, reusing read_state._spaced rather than
    inventing a second one. Takes the last path segment so a mod's
    `$moddir$_FS25_x/data/.../name.xml` shape degrades to the file's own
    name, never the mod folder. "" (never derives anything) when there is no
    filename to work from -- the preplaced case DEC-212 leaves on the
    id-derived fallback.
    """
    base = str(filename or "").strip()
    if not base:
        return ""
    base = base.replace("\\", "/").rsplit("/", 1)[-1]
    if base.lower().endswith(".xml"):
        base = base[:-4]
    return read_state._spaced(base) if base else ""


def _building_roots(defs_record, mods_dir):
    """The install and mods roots the cached production_defs read, taken from its own
    provenance (item 9): this emitter is never handed an install_dir, and the cache
    already names the one it was built from. None when the cache names no install root --
    build_points then marks every building `disabled`, so each capacity row is REFUSED with that
    reason. The recipe-path join does NOT stand in: it cannot tell two buildings that share a
    recipe apart (item 9, review M3)."""
    sources = (((defs_record.get("envelope") or {}).get("provenance") or {}).get("sources")
               or [])
    roots = {s.get("kind"): s.get("path") for s in sources if isinstance(s, dict)}
    install_dir = roots.get("install")
    if not install_dir:
        return None
    return {"install_dir": install_dir, "mods_dir": mods_dir or roots.get("mods")}


def load_defs_record(cache_dir):
    """The cached production_defs domain, AUDITED -- item 13c's rule verbatim.

    Returns (record, defs_as_of, None) or (None, None, reason).

    ⛔ NEVER TRUST THE CACHE. A cache_entry that is absent, that reports a
    status other than "ok", or that carries no generated_at is a REFUSAL, not a
    warning: every defs-derived figure on this tab would otherwise ship with no
    stamp and no basis, which is exactly the state the AS-OF mark exists to
    make impossible.
    """
    path = os.path.join(cache_dir, "%s.json" % DOMAIN_DEFS)
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except FileNotFoundError:
        return None, None, (
            "the production_defs cache is not at %s, so no recipe, output rate "
            "or storage capacity can be resolved. This is NOT a report that the "
            "farm has no productions." % path)
    except (json.JSONDecodeError, OSError) as exc:
        return None, None, "the production_defs cache at %s could not be read (%s)" % (path, exc)
    if not isinstance(record, dict):
        return None, None, "the production_defs cache at %s is not a JSON object" % path

    entry = record.get("cache_entry")
    if not isinstance(entry, dict):
        return None, None, (
            "the production_defs cache carries no cache_entry, so there is no "
            "generation status to audit and no as-of stamp to publish")
    if entry.get("status") != "ok":
        return None, None, (
            "the production_defs cache_entry reports status %r, so its sections "
            "cannot be believed. Its own failure: %r"
            % (entry.get("status"), (entry.get("failure") or {}).get("reason")))
    generated_at = entry.get("generated_at")
    if not generated_at:
        return None, None, (
            "the production_defs cache_entry carries no generated_at, so every "
            "definition-derived figure would ship with no as-of stamp")
    return record, str(generated_at), None


def index_recipes(defs_record):
    """production_id -> [candidate, ...] over BOTH recipe sections.

    ⛔ GREENHOUSE RECIPES ARE A SIBLING SECTION AND MUST BE CONSULTED.
    read_production_defs.py deliberately excludes greenhouse productions from
    `production_recipes`, but read_productions.py walks every <productionPoint>
    with no greenhouse filter -- so a greenhouse DOES produce a production_lines
    row. Reading production_recipes alone makes every greenhouse line report
    "no recipe carries this production_id": literally true of the one section
    consulted, substantively false about the farm.

    ⛔ AND IF greenhouse_recipes IS PRESENT BUT UNREADABLE THIS REFUSES rather
    than falling back, for the reason derive_production_demand states in its own
    words: a line with no match in production_recipes cannot be called unmatched
    when its recipe may be in the section that failed.

    Returns (index, consulted, reason). `reason` is fatal to the run.
    """
    index, consulted = {}, []
    rows, err = read_state._section_rows({DOMAIN_DEFS: defs_record},
                                         DOMAIN_DEFS, "production_recipes")
    if err:
        return None, None, err
    consulted.append("production_recipes")
    batches = [("production_recipes", rows)]

    if read_state._section_present({DOMAIN_DEFS: defs_record},
                                   DOMAIN_DEFS, "greenhouse_recipes"):
        gh_rows, gh_err = read_state._section_rows({DOMAIN_DEFS: defs_record},
                                                   DOMAIN_DEFS, "greenhouse_recipes")
        if gh_err:
            return None, None, (
                "production_defs.greenhouse_recipes is present but unreadable, "
                "so a line with no match in production_recipes cannot be called "
                "unmatched -- its recipe may be in the section that failed. The "
                "producer's own reason: %s" % gh_err)
        consulted.append("greenhouse_recipes")
        batches.append(("greenhouse_recipes", gh_rows))

    for section, batch in batches:
        for row in batch:
            if not isinstance(row, dict):
                continue
            pid = row.get("production_id")
            if not pid:
                continue
            index.setdefault(pid, []).append((section, row))
    return index, consulted, None


def index_capacities(defs_record):
    """(source_path, fill_type) -> capacity. The section's own identity fields.

    Returns (index, reason). A missing or unreadable section is a REASON: every
    o3 then renders `unknown` for a stated cause rather than looking like a farm
    whose tanks have no size.
    """
    rows, err = read_state._section_rows({DOMAIN_DEFS: defs_record},
                                         DOMAIN_DEFS, "storage_capacities")
    if err:
        return None, err
    index = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (row.get("source_path"), row.get("fill_type"))
        cap = _num(row.get("capacity"))
        if key[0] is None or key[1] is None or cap is None:
            continue
        index.setdefault(key, []).append(cap)
    return index, None


def line_output(candidates):
    """l3 + o1: what this line makes, and how fast. (fill_type, label, per_hour,
    status, reason).

    ⛔ THE SAME REFUSAL RULE AS THE BURN RATE, AND IT WAS NOT FREE.
    `outPerHour` is `first output amount x cycles_per_hour`, and both terms come
    from a recipe resolved through a `production_id` that DOES NOT IDENTIFY ONE
    RECIPE. So the output rate carries exactly the ambiguity BUG-026 names for
    the input rate, and it is refused the same way: candidates that disagree on
    the computed per-hour figure emit NO number.

    ⚠ THE OUTPUT FILL TYPE IS CHECKED FOR AGREEMENT SEPARATELY FROM THE RATE,
    and that is not pedantry. Two definitions can agree on WHAT a line makes
    while disagreeing on HOW FAST -- that is a known rate with an unknown
    quantity, not an unknown product -- and collapsing the two questions would
    throw away a fill type we can name. When the fill TYPE disagrees there is no
    row to draw at all.
    """
    fts, rates = [], []
    for _section, row in candidates:
        outputs = row.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            continue
        first = outputs[0]
        if not isinstance(first, dict):
            continue
        ft = first.get("fill_type")
        if ft:
            fts.append(ft)
        amount = _num(first.get("amount"))
        cph = _num(row.get("cycles_per_hour"))
        if amount is not None and cph is not None:
            rates.append(round(amount * cph, 4))

    ft, ft_spread = _agree(fts)
    if ft is None:
        if ft_spread:
            return None, None, None, "ambiguous", (
                "%d recipe definitions disagree on what this line's first output "
                "IS (%s), so no output row is drawn."
                % (len(fts), ", ".join(str(v) for v in ft_spread)))
        return None, None, None, "absent", (
            "no definition of this recipe declares an output, so nothing is "
            "known about what this line makes.")

    label = read_state._spaced(ft)
    per_hour, spread = _agree(rates)
    if per_hour is None:
        if spread:
            return ft, label, None, "ambiguous", (
                "%d recipe definitions disagree on this line's output rate "
                "(%s L/h), and a production_id does not identify one recipe, so "
                "no rate is emitted. Picking one would be wrong by the full spread."
                % (len(rates), ", ".join("%g" % v for v in spread)))
        return ft, label, None, "unreadable", (
            "this recipe's output amount or cycles_per_hour could not be read as "
            "a number, so no output rate is emitted.")
    return ft, label, per_hour, "resolved", None


def _own_file_note(why):
    return (" The building's own definition file could not settle it: %s." % why) if why else ""


def output_capacity(candidates, fill_type, capacities, building=None):
    """o3: (capacity, status, reason).

    ⛔⛔ THE REFUSAL RULE V-01 ADDED, AND IT IS THE MOST IMPORTANT LINE IN THIS
    FILE. `storage_capacities.identity_fields` is [source_path, fill_type]. It
    carries NO placeable id, and `production_points` cannot supply one, so the
    only documented route to a capacity is
    production_id -> recipe.source_path -> capacity -- and that route is NOT
    single-valued, for exactly the reason the burn rate is not.

    Measured on the live cache: of 38 point x output rows, 12 resolve, 25 are
    AMBIGUOUS and 1 is absent, with spreads to 100x --
    montanaDairy/CHEESE returns 4000 / 40000 / 400000 / 5000 L depending which
    row is picked.

    ⛔ SO AN AMBIGUOUS JOIN RENDERS `unknown` AND NEVER PICKS A CANDIDATE, and
    there is NO TIE-BREAK to build. Reporting a 4,000 L bin as 400,000 L is
    RSK-001 -- absence rendered as data, the failure this product exists to
    prevent.

    ⚠ ABSENCE WAS ALREADY HANDLED AND AMBIGUITY WAS NOT, WHICH IS THE WHOLE
    FINDING: an ambiguous join RETURNS VALUES, so an absence check never fires
    on it. Both statuses withhold the number here, and each says which it was.
    """
    # ITEM 9 (FM-1001): THE BUILDING'S OWN FILE FIRST. `building` carries the
    # placeable's saved `filename` and the install/mods roots; when it resolves, that
    # building's own ceiling is the answer, and the recipe-path join below -- which
    # cannot tell two buildings that share a recipe apart -- is never consulted.
    # NO FALLBACK ONCE A BUILDING IS KNOWN (review M3). If the building's own file gives a
    # figure it is the answer; if it does not -- the file says no row of its own, or it could
    # not be reached -- the row is REFUSED with that reason. The recipe-path join below cannot
    # tell two buildings that share a recipe apart, so a figure it produced for a building
    # whose own file could not be read would be a guess with no mark on it (the published
    # XML has no field that could mark it: a capacityReason on a row with a capacity reads as
    # a refusal). Measured on the owner's farm, the fallback added no row the own-file join
    # had not already resolved. `building is None` only for callers that carry no building.
    if building is not None:
        if building.get("disabled"):
            return None, "absent", building["disabled"]
        got, why, _kind = read_building_capacity.ceiling_for_fill_type(
            building.get("filename"), "productionPoint", fill_type,
            building.get("install_dir"), building.get("mods_dir"), building["cache"])
        if got is not None:
            return got, "resolved", None
        return None, "absent", why
    building_why = None

    values = []
    for _section, row in candidates:
        path = row.get("source_path")
        if not path:
            continue
        values.extend(capacities.get((path, fill_type), []))

    cap, spread = _agree(values)
    if cap is None:
        if spread:
            return None, "ambiguous", (
                "%d storage definitions disagree on this tank's capacity (%s L). "
                "storage_capacities is keyed [source_path, fill_type] and carries "
                "no placeable id, so nothing says which definition this building "
                "uses. No capacity and no fill percentage are emitted; picking one "
                "could be wrong by %gx."
                % (len(values), ", ".join("%g" % v for v in spread),
                   (max(spread) / min(spread)) if min(spread) else 0)
                + _own_file_note(building_why))
        return None, "absent", (
            "no storage_capacities row exists for this building's recipe source "
            "path and this fill type, so the tank's size is unknown. This is NOT "
            "a report that the tank has no capacity." + _own_file_note(building_why))
    return cap, "resolved", None


# ---------------------------------------------------------------------------
# TECH-DEBT-139 -- AN ABSENT STORAGE NODE IS A MEASURED ZERO, NOT AN UNKNOWN,
# AND "NEVER STARTED" IS A DIFFERENT CLAIM FROM "STARVING".
#
# ⛔ THE DEFECT THIS CLOSES IS DEC-001'S OWN CLASS, INVERTED. Everywhere else
# this file refuses to render absence as data. Here it did the opposite: it
# rendered DATA AS ABSENCE. The game never writes a production storage node at
# `fillLevel="0.000000"` -- it OMITS the node -- so "no node" is the game's way
# of saying EMPTY, and reporting it as `unknown` tells the player "I cannot
# tell" about the one state this tab exists to catch.
#
# MEASURED on the owner's savegame1 (2026-09-12, read-only), and the sweep
# carries its own non-zero control rather than resting on a bare zero:
#     /placeable/productionPoint/storage/node   93 nodes, 0 written as 0.0
#     /placeable/silo/storage/node              18 nodes, 0 written as 0.0
#     /placeable/husbandry/storage/node          5 nodes, 0 written as 0.0
#   CONTROL, same file, same parse -- other element kinds DO write zeros:
#     /placeable/bunkerSilo@fillLevel             2 written as 0.0
#     /placeable/husbandryMeadow/fillType         16 written as 0.0
# So the instrument can see a zero where one exists; 0-of-116 across three
# independent storage/node populations is the omission, not a blind spot.
#
# ⛔⛔ AND A NAIVE "MISSING NODE = 0" IS WRONG AND WOULD SHIP RSK-001.
# Some lines the owner has NEVER SUPPLIED. Flagging a never-started chain
# identically to a real stockout trains him to ignore the footer, which costs
# the tab the only thing it has. So the verdict is per production line:
#
#   NOT STARTED  <=> EVERY output of EVERY line drawing on this tank is also
#                    absent. Nothing has ever come out, so nothing ever went in.
#   EMPTY        <=> the input is absent but SOME output of SOME line drawing on
#                    this tank IS recorded. The recipe demonstrably fired, so the
#                    tank ran dry: a real stockout, treated as a measured 0.
#   unknown      <=> anything that cannot be decided. The word keeps its meaning.
#
# ⭐ WHY A RECORDED OUTPUT PROVES THE RECIPE FIRED, and this is the load-bearing
# premise, so it was measured rather than assumed: a nonzero output could only
# be a spawn default if some definition declared a starting level. Across ALL 84
# recipe source paths reachable from all 27 of the owner's points -- base game,
# map mod and third-party placeables, read out of their zips -- `fillLevel=`
# appears in ZERO of them, against a control of 506 occurrences in the savegame
# itself. The `<storage>` blocks carry capacity ceilings only. A production point
# therefore spawns with every tank empty, and an output in storage can only have
# been produced.
#
# ⛔ THE EXCEPTION, HANDLED RATHER THAN DOCUMENTED AWAY. A line whose output is
# auto-delivered or sold directly never banks output in the point's own storage,
# so the output test would read an actively-running direct-sell line as "never
# started" -- a false reassurance, the worst direction to be wrong in. That
# configuration IS readable: read_productions.py's `delivery_modes` section (b5)
# parses <autoDeliverFillType> / <directSellFillType>, whose PRESENCE is the
# configuration. A point carrying any delivery mode is refused a verdict on
# output-absence and stays honestly `unknown`, naming the exception.
#
# ⛔ IT FAILS CLOSED, THREE WAYS, and each guard exists because the failure it
# prevents would be invisible:
#   * storage_fill_levels unreadable -> EVERY node looks absent, so the whole
#     farm would publish as 0 L. No verdict is issued at all; `unknown` stands.
#   * delivery_modes unreadable -> the direct-sell exception cannot be ruled
#     out. No verdict; `unknown` stands.
#   * a line whose recipe declares no output at all -> the test has no evidence
#     to weigh. No verdict; `unknown` stands.
#
# ⚠ AND ABSENCE IS KEYED OFF storage_fill_levels, NEVER OFF THE DEMAND ENTRY.
# This is the single most dangerous line in the change. derive_production_demand
# deliberately emits NO `fill_level` on a PASS-THROUGH input, and says so in its
# own absence_guarantee: it conflates "no stock row" with "excluded as
# pass-through". Measured on savegame1: the two sources agree on 67 of 69 input
# entries and disagree on exactly the 2 pass-through rows, where the join says
# None and the savegame says 16,732.6 L and 17,625.6 L. Keying absence off the
# join would have published a 16,732 L tank as `0.0` -- a complete, plausible,
# correctly ordered lie, which is RSK-001 exactly.
# ---------------------------------------------------------------------------
STOCK_STOCKED = "stocked"
STOCK_EMPTY = "empty"
STOCK_NOT_STARTED = "notStarted"
STOCK_UNKNOWN = "unknown"


def line_output_fill_types(candidates):
    """Every output fill type this line could make, across EVERY candidate
    definition, plus whether an output was declared at all.

    Returns (fill_types, declared). `declared` is False when no candidate
    declares any output -- the one shape the output-presence test cannot weigh,
    and therefore a refusal rather than a "no outputs recorded" verdict.

    ⚠ THE UNION, NOT `outputs[0]`. line_output() takes the FIRST output because
    it is drawing ONE row and must not invent agreement across definitions. This
    asks a different question -- "has ANYTHING this line makes ever appeared" --
    and there the union is the honest set: the owner's sawmill declares PLANKS,
    BOARDS, WOODBEAM, PREFABWALL and WOODCHIPS, and taking only the first would
    throw away four fifths of the evidence that the line has run.
    """
    fts = set()
    declared = False
    for _section, row in candidates:
        outputs = row.get("outputs")
        if not isinstance(outputs, list):
            continue
        for out in outputs:
            if isinstance(out, dict) and out.get("fill_type"):
                fts.add(out.get("fill_type"))
                declared = True
    return fts, declared


def _line_label(line):
    """The label a line row publishes for this line.

    ⛔ ONE FUNCTION, TWO CALL SITES, ON PURPOSE. The <line name=...> a reader
    sees and the line a stateReason NAMES must be the same string, or the
    sentence refers to something the player cannot find in the tab -- and the
    cross-reference that proves the sentence honest stops resolving.
    """
    return (line.get("display_name")
            or read_state._spaced(line.get("production_id")))


def classify_absent_stock(pid, ft, lines, recipes, recorded_fts,
                          stock_readable, delivery_readable, delivery_fts):
    """The verdict for an input whose storage node is ABSENT.

    Returns (state, reason). `state` is STOCK_EMPTY, STOCK_NOT_STARTED or
    STOCK_UNKNOWN; `reason` is the sentence the tab shows, and is None only for
    STOCK_EMPTY, whose meaning is carried by the number itself.

    ⛔⛔ THE SCOPE IS PER LINE, AND `lines` IS EVERY LINE DRAWING ON **THIS
    TANK** -- NEVER EVERY LINE AT THE POINT ([[DEC-202]], which resolved an
    ambiguity in DEC-197: its rule text said per-line and its worked sawmill
    justification reasoned point-wide). The evidence weighed below is each
    line's OWN declared outputs against the point's storage, so a line has run
    iff something IT makes is recorded. One row is emitted per tank, so a tank
    several lines draw on is NOT STARTED only when every one of those lines is;
    a tank one of its consumers has demonstrably used has been supplied, and
    that aggregation is forced by the row granularity, not a second rule.

    ⛔ PASSING THE POINT'S `lines` HERE IS THE WRONG SCOPE AND THE COST IS
    MEASURED, not stylistic: on the owner's farm it moves notStarted 1 -> 0,
    empty 6 -> 7 and the urgent count 8 -> 9, and the extra urgent row is his
    soymilk line, which he has never made -- the exact false alarm DEC-197
    exists to prevent. The MULTILINE fixture point exists to fail that edit;
    NEVERSTART alone cannot, because a point with one line makes the two scopes
    identical, and a fixture that cannot contain the failure is not a fixture.
    """
    if not stock_readable:
        return STOCK_UNKNOWN, (
            "the savegame's storage levels could not be read at all, so an "
            "absent node cannot be told apart from an unmeasured one. This is "
            "NOT a report that the stock is zero.")
    if not delivery_readable:
        return STOCK_UNKNOWN, (
            "this farm's auto-delivery and direct-sale configuration could not "
            "be read, so a line that never banks its output cannot be told "
            "apart from a line that has never run. This is NOT a report that "
            "the stock is zero.")
    # ⛔ THE EXCEPTION IS SCOPED TO THE LINE, NOT THE BUILDING ([[DEC-202]]).
    # b5 records <autoDeliverFillType>/<directSellFillType> per FILL TYPE, and a
    # point with two independent lines -- one direct-sold, one normally banked --
    # would otherwise have BOTH inputs refused, leaving TECH-DEBT-139 open on the
    # line the evidence can perfectly well settle. 0 of 44 points on savegame1
    # carry either element, so no live number moves either way.
    #
    # ⚠ THE MATCH IS CASE-FOLDED HERE AND EXACT BELOW, and the asymmetry is the
    # same one stated at the output-evidence test: folding can only WIDEN this
    # refusal, which withholds a verdict. Requiring an exact match could
    # withdraw the exception from a line that really does sell its output and
    # publish "never started" for a line that may be starving -- wrong in the
    # reassuring direction, which is the worst direction.
    delivered = {str(x).casefold()
                 for x in delivery_fts.get(pid, ()) if x is not None}
    if delivered:
        for line in lines:
            sold, _declared = line_output_fill_types(
                recipes.get(line.get("production_id"), []))
            if {str(f).casefold() for f in sold} & delivered:
                return STOCK_UNKNOWN, (
                    "a line drawing on this tank auto-delivers or directly "
                    "sells its output, so that output never reaches storage and "
                    "an empty output tank cannot distinguish a line that has run "
                    "from one that never started. The input's stock is not "
                    "reported rather than guessed.")

    # ⛔⛔ THE CASE-MISMATCH REFUSAL, AND IT IS NOT HYPOTHETICAL -- IT FIRES ON
    # THE OWNER'S OWN SAVE. FS25 upper-cases fill-type tokens in places a mod's
    # own XML does not, so a recipe's declared input can be spelled differently
    # from the node the engine wrote. Measured on savegame1: FS25_LogisticsCenter
    # declares its pass-through as `soupCansPotato`, and the savegame records the
    # node as `SOUPCANSPOTATO`. The exact key therefore MISSES and the tank reads
    # as absent -- while it demonstrably holds material.
    #
    # ⛔ SO THIS IS THE ONE PLACE THE FIX COULD HAVE SHIPPED A CONFIDENT WRONG
    # NUMBER: without this guard that row publishes `held="0.0"` for a tank that
    # is not empty -- and, because a sibling definition spells the same output in
    # upper case, it is flagged `empty` (urgent) rather than merely mislabelled.
    # That is RSK-001, and strictly worse than the `unknown` this change removes.
    #
    # ⚠ AND THE ANSWER IS NOT TO CASE-FOLD THE LOOKUP. That would assert FS25's
    # fill-type id space is case-INSENSITIVE, which is an engine claim we have
    # not verified and must not invent (the corpus carries no Storage save page).
    # Two spellings might be one tank or two; from one snapshot we cannot tell.
    # That is precisely what `unknown` is for, so it is what we say.
    #
    # ⚠ "A FOLDED MATCH THAT IS NOT AN EXACT ONE" -- both halves are needed. An
    # exact match is trivially also a folded one, so testing the fold alone makes
    # this fire whenever the tank IS found, which is no mismatch at all. Harmless
    # on the shipped path (we only get here after the exact lookup missed) but
    # wrong -- and it silently disarmed a mutation gate, which is how it surfaced.
    folded = {str(x).casefold() for x in recorded_fts if x is not None}
    if (ft is not None and ft not in recorded_fts
            and str(ft).casefold() in folded):
        return STOCK_UNKNOWN, (
            "this building stores a fill type whose name differs from %r only in "
            "letter case, so the recipe's spelling and the savegame's spelling "
            "cannot be matched with confidence -- they may be one tank or two. "
            "The stock is not reported rather than guessed, and in particular it "
            "is NOT reported as zero." % (ft,))

    undeclared = []
    for line in lines:
        prod_id = line.get("production_id")
        fts, declared = line_output_fill_types(recipes.get(prod_id, []))
        if not declared:
            undeclared.append(prod_id)
            continue
        # ⚠ EXACT MATCH ON PURPOSE -- BUT IT IS NOT THE SAFE DIRECTION, AND AN
        # EARLIER VERSION OF THIS COMMENT SAID IT WAS. A case-mismatched OUTPUT
        # cannot count as evidence, so the loop falls through to STOCK_NOT_STARTED
        # -- it does NOT withhold a verdict. `unknown` withholds; `notStarted`
        # asserts, and it asserts the reassuring thing: a line that HAS run and is
        # now starving is published as one the owner never began, and excluded
        # from the urgent count. That is precisely the outcome the direct-sell
        # comment above calls "wrong in the reassuring direction, which is the
        # worst direction", and the two must not rate the same outcome opposite
        # ways -- a false all-clear read as a safe default is how it ships.
        #
        # ⛔ SO WHY EXACT? Because case-FOLDING here would assert that FS25's
        # fill-type id space is case-insensitive -- the same unverified engine
        # claim refused at the lookup guard above. The cost is real and is
        # accepted with its eyes open, not because it is safe. It is bounded by
        # that guard: a mismatch on the INPUT's own spelling is already refused
        # as `unknown`, so this can only bite an output whose spelling differs
        # while the input's does not.
        if fts & recorded_fts:
            # ⭐ THE RECIPE FIRED. No definition of any of this farm's points
            # declares a starting fill level, so a recorded output was produced,
            # which means this input was once supplied and has since run out.
            return STOCK_EMPTY, None
    if undeclared:
        return STOCK_UNKNOWN, (
            "no definition of %s declares an output, so there is no evidence "
            "either way about whether this line has ever run. The input's "
            "stock is not reported rather than guessed."
            % ", ".join(str(p) for p in sorted(set(undeclared))))
    # ⛔⛔ THE SENTENCE IS ABOUT THE LINE, NOT THE BUILDING ([[DEC-202]]), AND
    # THE BUILDING FORM WAS FALSE ON THE OWNER'S ONLY LIVE INSTANCE OF IT. His
    # montanaDairy row read "nothing this building produces has ever appeared in
    # its storage" while, six lines below in the SAME <point>, that building's
    # own output rows published BUTTER 631.8, CHEESE 23.0, BUFFALOMOZZARELLA
    # 372.0, BUFFALOMILK_BOTTLED 471.3 and MILK_BOTTLED 719.8. Five things it
    # produces were in its storage as the document said none were.
    #
    # ⭐ NAMING THE LINES IS WHAT MAKES THE CLAIM CHECKABLE: the labels are the
    # same strings the <line> rows carry (_line_label), so a reader -- and the
    # gate -- can resolve each name against the outputs actually banked.
    named = ", ".join(sorted({_line_label(line) for line in lines}))
    return STOCK_NOT_STARTED, (
        "no output of %s has ever appeared in this building's storage, so this "
        "line has never been supplied. The tank is empty, but this is a line "
        "that has not been started -- not a production that has run dry. Other "
        "lines in this building may well have run."
        % (named or "this line",))


def classify_absent_output(ft, recorded_fts, stock_readable):
    """The verdict for an OUTPUT whose storage node is ABSENT ([[DEC-203]]).

    Returns (held, reason): `(0.0, None)` when the absence is a MEASURED zero,
    `(None, sentence)` when it cannot be told from an unmeasured tank.

    ⛔⛔ THE SAME FACT WAS READ TWO OPPOSITE WAYS INSIDE ONE RECORD, AND THAT IS
    WHY THIS EXISTS. classify_absent_stock() treats a missing node as positive
    evidence that a line never ran, while the output branch used to render the
    identical absence as "the manager cannot see what is stored. This is NOT a
    report that the tank is empty." On the owner's farm `montanaDairy/SOYMILK`
    was BOTH -- the proof his soy line never ran AND the denial that its tank is
    empty -- in the same <point>. `bakeryUS/CAKE` was the second instance.

    The premise is the one already proved for inputs and re-measured this turn:
    0 of 93 productionPoint storage nodes on savegame1 are written as
    fillLevel="0.0" and 0 omit the attribute, so the game OMITS an empty node
    rather than writing a zero.

    ⚠ THE TWO REFUSALS ARE NOT OPTIONAL, and the second is RSK-001 exactly. An
    unreadable stock index makes every node look absent, so a verdict drawn from
    it would publish 0 L across the whole farm; and FS25 upper-cases fill-type
    tokens where a mod's own XML does not, so an exact-key miss on a differently
    cased spelling would publish a tank holding thousands of litres as `0.0`.
    Neither is a report that the tank is empty, and `unknown` keeps its meaning
    (DEC-001).

    ⚠ NO DIRECT-SELL EXCEPTION HERE, deliberately. That guard exists on the
    INPUT side because a direct-sold output never reaching storage destroys the
    evidence about whether the LINE ran. It says nothing against the output
    tank's own level: a tank whose product is sold on the spot really does hold
    nothing, and the absent node measures exactly that.
    """
    if not stock_readable:
        return None, (
            "the savegame's storage levels could not be read at all, so an "
            "absent node cannot be told apart from an unmeasured one. This is "
            "NOT a report that the tank is empty.")
    folded = {str(x).casefold() for x in recorded_fts if x is not None}
    if (ft is not None and ft not in recorded_fts
            and str(ft).casefold() in folded):
        return None, (
            "this building stores a fill type whose name differs from %r only in "
            "letter case, so the recipe's spelling and the savegame's spelling "
            "cannot be matched with confidence -- they may be one tank or two. "
            "The stock is not reported rather than guessed, and in particular it "
            "is NOT reported as zero." % (ft,))
    return 0.0, None


def _resolve_point_name(prow, pid):
    """(name, name_source, name_reason) for one production_points row.

    Split out of build_points() so the DISPLAYED name can be computed for
    every point BEFORE any of them is disambiguated -- D5 needs the full set
    to tell a genuine collision from a point merely not visited yet.
    """
    raw_name = (prow.get("placeable_name") or "").strip()
    if raw_name and raw_name != "<unnamed>":
        return raw_name, "literal", None
    # ⛔⛔ DEC-212. A failed resolution WITH a filename gets a readable label
    # derived from the FILE name, never the hex uniqueId (H1) -- and the
    # stated reason travels with it, rather than the player seeing neither a
    # name nor a cause. Only a genuinely nameless preplaced point (no
    # filename at all -- nothing to resolve, nothing to derive from) keeps
    # today's id-derived label.
    filename = (prow.get("filename") or "").strip()
    name = _title_from_filename(filename) if filename else ""
    if not name:
        name = _title_from_id(pid)
    name_reason = None
    reasons = prow.get("name_unresolved_reason")
    if isinstance(reasons, list) and reasons:
        name_reason = reasons[0]
    return name, "derived", name_reason


def _disambiguate_displayed_names(entries):
    """D5, applied to the FINAL DISPLAYED name (Parzival's clarification of
    DEC-212, 2026-09-16, correcting DEC-212's own worked example -- that
    example was ONE building and was never meant to exempt a derived
    duplicate from D5).

    Two rows whose displayed name is identical get a stable " #N" suffix, N
    assigned in DOCUMENT ORDER -- mirrors read_productions.disambiguate_names()'s
    exact algorithm (a per-name counter, "<unnamed>" excluded) rather than
    inventing a second one, so re-running against an unchanged save reproduces
    the same suffixes.

    ⚠ THIS RUNS *IN ADDITION TO*, NOT INSTEAD OF, read_productions.py's OWN
    PASS. That pass already made every RESOLVED literal duplicate a unique
    string (e.g. "Hydroponics Greenhouse Large #1"/"#2") before this file ever
    sees it, so it is a no-op here -- one occurrence each, nothing to do. What
    it cannot see is a DERIVED collision: two placeables that both fail
    resolution to the identical "<unnamed>" sentinel (which that pass
    deliberately excludes) become identical STRINGS only once THIS file
    derives a label from their file name -- a collision no earlier stage can
    observe. Keying by the name STRING itself is also why "a resolved pair
    and a derived pair must not share one counter": two different collision
    groups (two hydroponic AND two mushroom greenhouses) never interact,
    because they are different keys, and each starts back at #1.

    "<unnamed>" is excluded for the same reason read_productions.py excludes
    it: it should never reach here as a DISPLAYED name post-derivation, but
    if something ever did, suffixing the sentinel would silently disarm the
    fallback that renders it.
    """
    counts = {}
    for entry in entries:
        if entry["name"] != "<unnamed>":
            counts[entry["name"]] = counts.get(entry["name"], 0) + 1
    seen = {}
    for entry in entries:
        name = entry["name"]
        if name == "<unnamed>" or counts[name] <= 1:
            continue
        seen[name] = seen.get(name, 0) + 1
        entry["name"] = "%s #%d" % (name, seen[name])


def build_points(fresh, demand, recipes, capacities, tally, building_roots=None):
    """The document's point rows. One per production POINT, never per line.

    ⛔ BUILT FROM `production_points`, NOT FROM `production_lines`. A point with
    no configured line emits no line row and would VANISH from a lines-derived
    list: on the live save the farm owns 27 points and 23 carry a line, so 4
    points -- one of them a base-game placeable reached by ordinary play --
    would silently disappear. The label would promise owned production points
    and the code would deliver configured ones.
    """
    sections = fresh.get("sections") or {}
    points_block = sections.get("production_points")
    if not isinstance(points_block, dict):
        return None, [], "read_productions.py returned no production_points section"
    if points_block.get("status") not in read_state.READABLE_SECTION_STATUS:
        return None, [], (
            "read_productions.py could not measure this farm's production points "
            "(production_points status: %r)" % (points_block.get("status"),))
    point_rows = points_block.get("data")
    if not isinstance(point_rows, list):
        return None, [], "read_productions.py's production_points section carried no rows"

    stock_block = sections.get("storage_fill_levels") or {}
    stock = {}
    # ⛔ TECH-DEBT-139: READABILITY IS TRACKED, NOT INFERRED FROM EMPTINESS. An
    # unreadable section leaves `stock` empty, which is indistinguishable from a
    # farm whose every tank is absent -- and absence is now load-bearing, so a
    # verdict drawn from an empty-because-broken index would publish 0 L across
    # the whole farm. classify_absent_stock() refuses outright without this flag.
    stock_readable = stock_block.get("status") in read_state.READABLE_SECTION_STATUS
    recorded_fts = {}
    if stock_readable:
        for row in (stock_block.get("data") or []):
            if isinstance(row, dict):
                key = (row.get("placeable_id"), row.get("fill_type"))
                if key not in stock:
                    stock[key] = _num(row.get("fill_level"))
                recorded_fts.setdefault(row.get("placeable_id"), set()).add(
                    row.get("fill_type"))

    # ⛔ TECH-DEBT-139's NAMED EXCEPTION. b5's PRESENCE is the configuration, so
    # an empty-but-read section is a real observation ("no output is configured
    # for delivery") and is `unknown_by_design`, not a failure -- which is why
    # READABLE_SECTION_STATUS is the test and a zero count is not.
    delivery_block = sections.get("delivery_modes") or {}
    delivery_readable = (
        delivery_block.get("status") in read_state.READABLE_SECTION_STATUS)
    delivery_fts = {}
    if delivery_readable:
        for row in (delivery_block.get("data") or []):
            if isinstance(row, dict) and row.get("placeable_id"):
                delivery_fts.setdefault(row.get("placeable_id"), set()).add(
                    row.get("fill_type"))

    demand_rows = demand.get("data") if isinstance(demand.get("data"), list) else []
    by_point = {}
    for row in demand_rows:
        if isinstance(row, dict):
            by_point.setdefault(row.get("placeable_id"), []).append(row)

    # PASS 1 -- resolve every point's DISPLAYED name before any of them is
    # disambiguated (D5 needs the full set to tell a genuine collision from a
    # point merely not visited yet, exactly like read_productions.py's own
    # pre-pass one layer down).
    named = []
    for prow in point_rows:
        if not isinstance(prow, dict):
            continue
        pid = prow.get("placeable_id")
        name, name_source, name_reason = _resolve_point_name(prow, pid)
        if name_source == "derived":
            tally["points_with_a_derived_name"] += 1
        named.append({"pid": pid, "name": name, "name_source": name_source,
                      "name_reason": name_reason,
                      "filename": (prow.get("filename") or "").strip()})
    _disambiguate_displayed_names(named)

    building_cache = {}
    points, unresolved = [], []
    for entry in named:
        pid, name = entry["pid"], entry["name"]
        name_source, name_reason = entry["name_source"], entry["name_reason"]
        if building_roots is not None:
            building = {"filename": entry["filename"], "cache": building_cache,
                        "install_dir": building_roots.get("install_dir"),
                        "mods_dir": building_roots.get("mods_dir")}
        else:
            building = {"filename": entry["filename"], "cache": building_cache,
                        "disabled": ("the cached production_defs names no game install "
                                     "root, so the building's own definition file could "
                                     "not be read; no capacity is given for it")}

        lines = by_point.get(pid, [])
        point = {"id": pid, "name": name, "name_source": name_source,
                 "name_reason": name_reason,
                 "inputs": [], "lines": [], "outputs": []}
        tally["points_total"] += 1
        if not lines:
            tally["points_with_no_configured_line"] += 1

        # -- section 1: INPUTS, one row per fill type this POINT consumes ----
        # ⛔ DEDUPLICATED BY FILL TYPE, NOT BY LINE. storage_fill_levels is keyed
        # per PLACEABLE: one <productionPoint> holds several <production> lines
        # that share one physical tank. Emitting a row per (line, fill type)
        # would show one tank several times with the same litres, reading as
        # several tanks' worth of stock.
        #
        # ⭐ AND THE RUNWAY IS ALREADY THE COMBINED ONE. derive_production_demand
        # divides the level by the rate summed over EVERY line drawing on the
        # tank, so hours_to_empty is identical across the sharers and taking any
        # of them is taking the combined answer -- not one line's optimistic view.
        seen_ft = {}
        # ⛔ TECH-DEBT-139 needs the LINES drawing on each tank, not just their
        # input entries: the not-started test is a question about a line's
        # OUTPUTS, which an input entry does not carry.
        entries_lines = {}
        for line in lines:
            for entry in (line.get("inputs") or []):
                ft = entry.get("fill_type")
                seen_ft.setdefault(ft, []).append(entry)
                entries_lines.setdefault(ft, []).append(line)
        for ft, entries in seen_ft.items():
            tally["input_rows_total"] += 1
            first = entries[0]
            row = {"ft": ft,
                   "label": first.get("fill_type_label") or read_state._spaced(ft)}

            # ⛔ TECH-DEBT-139. ABSENCE IS KEYED OFF storage_fill_levels, NEVER
            # OFF THE DEMAND ENTRY. The join emits no `fill_level` on a
            # pass-through input, conflating "no stock row" with "excluded as
            # pass-through" (its own absence_guarantee says so). Measured: the
            # two agree on 67 of 69 entries on savegame1 and disagree on exactly
            # the 2 pass-through rows, where the join says None and the savegame
            # says 16,732.6 L and 17,625.6 L. Reading the join as absence would
            # publish those tanks as `0.0`.
            held = _num(first.get("fill_level"))
            if held is None and stock_readable:
                held = stock.get((pid, ft))
            # ⛔ A NODE PRESENT AT ZERO ASKS THE SAME QUESTION AS A MISSING
            # ONE, AND IT USED TO SKIP THE TEST ENTIRELY. `held == 0` went
            # straight to `empty` -- flagged, urgent -- without ever consulting
            # the line's outputs, so DEC-202's not-started condition was never
            # evaluated on this route. The game does not write that shape today
            # (0 of 93 nodes on savegame1, re-measured this turn, and 0 omit
            # `fillLevel` either), but savegame_placeables.xsd:1247 declares
            # `default="0"` on the attribute and read_productions.py already
            # honours it, so it is a schema-legal way for the game or a mod to
            # say zero -- and this file's own DAIRY fixture uses it, which means
            # a PASSING TEST was locking the divergence in.
            #
            # ⚠ THE MEASUREMENT IS NEVER DISCARDED. A present zero is a real
            # reading, so an undecidable never-started test cannot turn it back
            # into `unknown`: the verdict falls back to `empty`, which is both
            # the measured answer and the conservative (flagging) one.
            if held is not None and held != 0:
                row["held"] = _round(held, 1)
                row["stockState"] = STOCK_STOCKED
            else:
                node_present = held is not None
                state, why = classify_absent_stock(
                    pid, ft, entries_lines.get(ft, []), recipes,
                    recorded_fts.get(pid, set()),
                    stock_readable, delivery_readable, delivery_fts)
                if node_present and state == STOCK_UNKNOWN:
                    state, why = STOCK_EMPTY, None
                row["stockState"] = state
                if state == STOCK_UNKNOWN:
                    tally["input_rows_held_unknown"] += 1
                    # ⚠ THE CLASSIFIER'S REASON WINS OVER THE JOIN'S. The join
                    # says only "no storage_fill_levels row exists ... this is
                    # NOT a report that the stock is zero" -- which is the
                    # generic sentence TECH-DEBT-139 was filed about, and it is
                    # now the LEAST informative thing we can say. `why` names the
                    # actual cause (direct sale, an unreadable section, a recipe
                    # with no declared output), which is what makes the remaining
                    # `unknown`s honest instead of lazy.
                    row["heldReason"] = why or first.get("stock_reason")
                else:
                    # ⭐ THE GAME OMITS AN EMPTY NODE, SO THIS IS A MEASUREMENT.
                    # Both verdicts publish the real 0; only the URGENCY differs,
                    # and `stockState` is what carries that difference to the tab.
                    row["held"] = _round(0.0, 1)
                    if state == STOCK_EMPTY:
                        tally["input_rows_empty_measured_zero"] += 1
                    else:
                        tally["input_rows_not_started"] += 1
                        row["stateReason"] = why

            statuses = {e.get("rate_status") for e in entries}
            if statuses == {"excluded"}:
                row["rate"] = "excluded"
                row["reason"] = first.get("note") or (
                    "this fill type is both an input and an output of every "
                    "definition of this recipe, so it passes through the building "
                    "rather than being consumed.")
                tally["input_rows_excluded_pass_through"] += 1
                point["inputs"].append(row)
                continue

            usable = [e for e in entries if e.get("rate_status") == "resolved"]
            if len(usable) == len([e for e in entries if e.get("rate_status") != "excluded"]):
                # Every line drawing on this tank resolved its own rate, so the
                # point-level burn is their SUM -- the rate that actually empties
                # the tank, which is the same denominator hours_to_empty used.
                total = sum(_num(e.get("per_hour")) or 0.0 for e in usable)
                row["perHour"] = _round(total, 2)
                row["rate"] = "resolved"
                tally["input_rows_rate_resolved"] += 1
            else:
                bad = next((e for e in entries
                            if e.get("rate_status") in ("ambiguous", "unreadable")), None)
                row["rate"] = (bad or {}).get("rate_status") or "unknown"
                row["reason"] = (bad or {}).get("reason") or (
                    "this input's burn rate could not be resolved, so no rate and "
                    "no runway are emitted.")
                if row["rate"] == "ambiguous":
                    tally["input_rows_rate_ambiguous"] += 1
                else:
                    tally["input_rows_rate_unreadable"] += 1

            hours = next((_num(e.get("hours_to_empty")) for e in entries
                          if _num(e.get("hours_to_empty")) is not None), None)
            # ⛔ TECH-DEBT-139 -- 0 LITRES DIVIDED BY ANY BURN RATE IS 0 HOURS,
            # SO AN AMBIGUOUS RATE DOES NOT MAKE THE RUNWAY UNKNOWN. The join
            # computes no hours_to_empty for an absent node (it had no level to
            # divide), and on an ambiguous rate it refuses the rate -- correctly.
            # But the runway of an EMPTY tank does not depend on the rate at all:
            # it is starved NOW. This is the tab's most important state, and it
            # was the one being reported as `unknown`.
            #
            # ⚠ GUARDED, AND THE GUARD IS NOT DECORATION: a rate that is KNOWN to
            # be 0 means nothing consumes this input, so it never empties and
            # 0/0 is not 0 -- it is undefined. A wholly unreadable rate earns no
            # runway either: with no rate known at all there is no arithmetic to
            # stand on.
            #
            # ⛔ THE TEST IS THE SUM, NOT THE MINIMUM, AND read_state IS THE
            # REFERENCE: derive_production_demand divides by the COMBINED rate
            # summed over every line drawing on the tank, and treats only a
            # combined 0 as "will never run dry". `min(known) > 0` refused a
            # runway whenever ANY line's rate was known to be 0 -- true for a
            # single line, false for a shared tank, where line A at 0 L/h and
            # line B at 5 L/h still drain it. That withheld a TRUE starved-now
            # flag, which is the safe direction but still a wrong answer.
            # ⛔⛔ A NEVER-STARTED LINE IS NOT STARVING, AND ON THE PRESENT-ZERO
            # ROUTE THE JOIN HANDS US A RUNWAY ANYWAY. derive_production_demand
            # sees a real level of 0.0 and a resolved rate and computes a
            # perfectly correct hours_to_empty of 0.0 -- so without this, a line
            # the owner has never begun lands in the urgent count with a runway
            # it inherited from arithmetic, which is precisely the false alarm
            # DEC-197 exists to prevent. The absent-node route never showed this
            # because the join emits no hours when it had no level to divide.
            if row.get("stockState") == STOCK_NOT_STARTED:
                hours = None
            if hours is None and row.get("stockState") == STOCK_EMPTY:
                known = [_num(e.get("per_hour")) for e in entries]
                known = [v for v in known if v is not None]
                if known and sum(known) > 0:
                    hours = 0.0
            if hours is not None:
                row["hoursToEmpty"] = _round(hours, 2)
                tally["input_rows_with_hours_to_empty"] += 1
                if hours == 0:
                    tally["input_rows_starved_now"] += 1
            else:
                why = next((e.get("hours_to_empty_reason") for e in entries
                            if e.get("hours_to_empty_reason")), None)
                if why:
                    row.setdefault("reason", why)
            point["inputs"].append(row)

        # -- section 2: PRODUCTION LINES, one row per line ------------------
        for line in lines:
            pid_line = line.get("production_id")
            tally["lines_total"] += 1
            if line.get("resolution") == "unmatched":
                tally["lines_unmatched"] += 1
                unresolved.append({
                    "id": "%s / %s" % (pid, pid_line),
                    "reason": line.get("reason") or "this line matched no recipe.",
                })
                continue

            candidates = recipes.get(pid_line, [])
            row = {"id": pid_line, "name": _line_label(line)}
            # ⚠ A DERIVED LABEL IS MARKED AS ONE. 678 of 748 recipe names in the
            # corpus are $l10n_ keys or %s templates whose text lives inside the
            # packed dataS.gar and is not readable from disk, so most of these
            # labels are derived from the production_id rather than authored.
            if line.get("display_name_source") == "derived_from_production_id":
                row["nameSource"] = "derived"
            enabled = line.get("is_enabled")
            if enabled in ("true", "false", True, False):
                row["enabled"] = "true" if enabled in ("true", True) else "false"

            ft, label, per_hour, status, reason = line_output(candidates)
            if per_hour is not None:
                row["outPerHour"] = _round(per_hour, 2)
                tally["lines_output_rate_resolved"] += 1
            else:
                row["outReason"] = reason
                if status == "ambiguous":
                    tally["lines_output_rate_ambiguous"] += 1
                else:
                    tally["lines_output_rate_absent"] += 1

            # l4: the input of THIS line with the smallest runway -- the one that
            # will starve it first. Unknown when no input of the line carries one.
            limiting, best = None, None
            for entry in (line.get("inputs") or []):
                h = _num(entry.get("hours_to_empty"))
                if h is not None and (best is None or h < best):
                    best, limiting = h, entry.get("fill_type_label") or entry.get("fill_type")
            if limiting is not None:
                row["limitingInput"] = limiting
            point["lines"].append(row)

            # -- section 3: OUTPUT STORAGE, one row per output fill type -----
            if ft is not None and not any(o["ft"] == ft for o in point["outputs"]):
                orow = {"ft": ft, "label": label}
                tally["output_rows_total"] += 1
                held = stock.get((pid, ft))
                if held is None:
                    # ⭐ [[DEC-203]]: AN ABSENT OUTPUT NODE IS A MEASURED ZERO
                    # TOO -- the same premise, the same savegame, the same loop.
                    held, why = classify_absent_output(
                        ft, recorded_fts.get(pid, set()), stock_readable)
                    if held is None:
                        tally["output_rows_held_unknown"] += 1
                        orow["heldReason"] = why
                    else:
                        tally["output_rows_empty_measured_zero"] += 1
                if held is not None:
                    orow["held"] = _round(held, 1)
                cap, cap_status, cap_reason = output_capacity(candidates, ft, capacities, building)
                if cap is not None:
                    orow["capacity"] = _round(cap, 1)
                    tally["output_rows_capacity_resolved"] += 1
                else:
                    orow["capacityReason"] = cap_reason
                    if cap_status == "ambiguous":
                        tally["output_rows_capacity_ambiguous"] += 1
                    else:
                        tally["output_rows_capacity_absent"] += 1
                point["outputs"].append(orow)

        points.append(point)
    return points, unresolved, None


def build_xml(points, unresolved, savegame_key, generated_at, farm_id, defs_as_of):
    """⛔ AN ATTRIBUTE THAT CANNOT BE RESOLVED IS ABSENT, never `0` and never "".

    `perHour` and `hoursToEmpty` are simply not written on an ambiguous row and
    `reason` carries why; `capacity` is not written on an ambiguous or absent
    join and `capacityReason` carries why. A blank and a zero are both absence
    dressed as data, and the reader turns an absent attribute into the WORD
    `unknown` -- never a dash, never an empty cell.

    ⚠ `held` IS THE ONE EXCEPTION, AND IT IS NOT A WEAKENING OF THE RULE
    (TECH-DEBT-139). An absent storage node is how the game writes a zero, so a
    `held="0.0"` on a node-absent row is a MEASUREMENT, not a default -- and
    `stockState` says which measurement it is (`empty` = ran dry, flag it;
    `notStarted` = never supplied, do not). A row that is genuinely undecidable
    still carries NO `held`, `stockState="unknown"` and a `heldReason`.

    ⚠ AND IT COVERS OUTPUT ROWS THE SAME WAY ([[DEC-203]]). An output row has no
    urgency to carry, so it publishes no `stockState`: `held="0.0"` is the
    measured zero and an ABSENT `held` with a `heldReason` is the refusal. The
    two are distinguishable without a third attribute, and inventing one would
    be schema the reader does not need.

    ⛔ TWO STAMPS, NOT ONE. `generatedAt` covers every savegame-derived figure;
    `defsAsOf` covers every definition-derived one. They can differ by weeks.
    """
    def attrs(pairs):
        return "".join(" %s=%s" % (k, quoteattr(str(v))) for k, v in pairs if v is not None)

    body = []
    for p in points:
        body.append('\n  <point%s>' % attrs([
            ("id", p["id"]), ("name", p["name"]), ("nameSource", p["name_source"]),
            ("nameReason", p.get("name_reason"))]))
        for r in p["inputs"]:
            body.append('\n    <input%s/>' % attrs([
                ("ft", r.get("ft")), ("label", r.get("label")),
                ("held", r.get("held")), ("perHour", r.get("perHour")),
                ("hoursToEmpty", r.get("hoursToEmpty")), ("rate", r.get("rate")),
                ("stockState", r.get("stockState")),
                ("reason", r.get("reason")), ("heldReason", r.get("heldReason")),
                ("stateReason", r.get("stateReason"))]))
        for r in p["lines"]:
            body.append('\n    <line%s/>' % attrs([
                ("id", r.get("id")), ("name", r.get("name")),
                ("nameSource", r.get("nameSource")), ("enabled", r.get("enabled")),
                ("outPerHour", r.get("outPerHour")),
                ("limitingInput", r.get("limitingInput")),
                ("outReason", r.get("outReason"))]))
        for r in p["outputs"]:
            body.append('\n    <output%s/>' % attrs([
                ("ft", r.get("ft")), ("label", r.get("label")),
                ("held", r.get("held")), ("capacity", r.get("capacity")),
                ("heldReason", r.get("heldReason")),
                ("capacityReason", r.get("capacityReason"))]))
        body.append('\n  </point>')
    for u in unresolved:
        body.append('\n  <unresolved%s/>' % attrs([("id", u["id"]), ("reason", u["reason"])]))

    return (
        '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        '<%s schema=%s generatedAt=%s savegame=%s farmId=%s defsAsOf=%s>%s\n'
        '</%s>\n'
    ) % (ROOT_TAG, quoteattr(str(SCHEMA_VERSION)), quoteattr(generated_at),
         quoteattr(savegame_key), quoteattr(str(farm_id)), quoteattr(defs_as_of),
         "".join(body), ROOT_TAG)


def published_points(path):
    """Which <point> ids the document already on disk publishes, and whether it
    could be READ at all. Returns (ids, readable).

    ⛔ THE IDS, NOT A COUNT -- emit_farm_xml.py's guard, and its reasoning holds
    verbatim here: a degraded run that loses one point while gaining another
    passes a cardinality check and overwrites. A present-but-unreadable document
    yields readable=False, because not being able to READ one is not evidence
    that it holds nothing.
    """
    try:
        with open(path, encoding="utf-8") as f:
            root = ET.parse(f).getroot()
    except FileNotFoundError:
        return set(), True
    except ET.ParseError:
        return set(), True
    except OSError:
        return set(), False
    if root.tag != ROOT_TAG:
        return set(), True
    return {p.get("id") for p in root.findall("point") if p.get("id")}, True


def atomic_write(path, text):
    """Write-then-rename. The mod reads this file on tab open; a reader must
    never catch a half-written one and conclude the farm has no productions."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".productions-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def collect(savegame_dir, farm_id, cache_dir, mode, mods_dir=None):
    """Everything up to the document. Returns (points, unresolved, meta, notes).

    `meta` carries the two stamps and the freshness verdicts; `notes` is the
    DEGRADED-MEASUREMENT channel that gates the refusal and the exit code.

    ⛔ `mods_dir`, THREADED THROUGH TO read_productions.py (fix round 1, D4/D5):
    without it every mod-backed production point falls back to `<unnamed>` and a
    real store name never reaches this document -- D4's logic was correct and
    unreachable, exactly the defect this parameter closes. `mods_dir=None` is a
    real, supported state (best-effort, matches read_productions.py's own
    contract): this domain still runs and every row that cannot resolve carries
    its own stated reason, never a crash and never a silently thinner document.
    No `install_dir` here on purpose -- it only changes a REFUSAL's wording for
    base-game placeables (their l10n is packed and unreadable either way) and is
    never available at this call's own caller (refresh_state.py only resolves
    mods_dir, the same shape publish_farm_tab/publish_fields_tab already use).
    """
    notes = []
    tally = {
        "points_total": 0,
        "points_with_no_configured_line": 0,
        "points_with_a_derived_name": 0,
        "lines_total": 0,
        "lines_unmatched": 0,
        "lines_output_rate_resolved": 0,
        "lines_output_rate_ambiguous": 0,
        "lines_output_rate_absent": 0,
        "input_rows_total": 0,
        "input_rows_rate_resolved": 0,
        "input_rows_rate_ambiguous": 0,
        "input_rows_rate_unreadable": 0,
        "input_rows_excluded_pass_through": 0,
        "input_rows_held_unknown": 0,
        # TECH-DEBT-139: the three verdicts an absent storage node now earns.
        # `input_rows_held_unknown` keeps its meaning -- rows publishing NO
        # number -- so the before/after is readable straight off the summary.
        "input_rows_empty_measured_zero": 0,
        "input_rows_not_started": 0,
        "input_rows_with_hours_to_empty": 0,
        "input_rows_starved_now": 0,
        "output_rows_total": 0,
        "output_rows_capacity_resolved": 0,
        "output_rows_capacity_ambiguous": 0,
        "output_rows_capacity_absent": 0,
        "output_rows_held_unknown": 0,
        "output_rows_empty_measured_zero": 0,
    }

    extra_args = ["--mods-dir", mods_dir] if mods_dir else None
    fresh = collect_state.run("read_productions.py", savegame_dir, farm_id=farm_id,
                              extra_args=extra_args)
    if not isinstance(fresh, dict) or "error" in fresh:
        why = fresh.get("error") if isinstance(fresh, dict) else "unusable output"
        return None, None, {"tally": tally}, ["read_productions.py: %s" % why]

    defs_record, defs_as_of, why = load_defs_record(cache_dir)
    if why:
        return None, None, {"tally": tally}, [why]

    # ⛔ BOTH VERDICTS ARE EARNED. production_defs goes through verify_domain
    # (it has a cache_entry); the freshly-run productions half goes through
    # verify_fresh_envelope, which performs the SAME source-set re-hash minus
    # the cache_entry lookup that has nothing to look up. See V-20 above.
    defs_status, defs_reason, defs_detail = read_state.verify_domain(defs_record, mode=mode)
    fresh_status, fresh_reason, fresh_detail = verify_fresh_envelope(fresh, mode=mode)

    domain_status = {DOMAIN_SAVEGAME: fresh_status, DOMAIN_DEFS: defs_status}
    domain_checks = {
        DOMAIN_SAVEGAME: {"freshness_check": (fresh_detail or {}).get("freshness_check"),
                          "comparison": (fresh_detail or {}).get("comparison")},
        DOMAIN_DEFS: {"freshness_check": (defs_detail or {}).get("freshness_check"),
                      "comparison": (defs_detail or {}).get("comparison")},
    }
    if fresh_status != "ok":
        notes.append("the freshly-run productions domain did not verify: %s"
                     % (fresh_reason or fresh_status))
    if defs_status != "ok":
        notes.append("the cached production_defs domain did not verify: %s"
                     % (defs_reason or defs_status))

    records = {DOMAIN_SAVEGAME: {"envelope": fresh}, DOMAIN_DEFS: defs_record}
    demand = read_state.derive_production_demand(
        records, domain_status=domain_status, domain_checks=domain_checks,
        accepted_stale=False)
    if demand.get("status") not in read_state.READABLE_SECTION_STATUS:
        notes.append("the production demand join reports status %r: %s"
                     % (demand.get("status"), demand.get("reason")))

    recipes, consulted, why = index_recipes(defs_record)
    if why:
        return None, None, {"tally": tally}, notes + [why]
    capacities, cap_why = index_capacities(defs_record)
    if cap_why:
        capacities = {}
        notes.append(cap_why)

    points, unresolved, why = build_points(fresh, demand, recipes, capacities, tally,
                                           building_roots=_building_roots(defs_record, mods_dir))
    if why:
        return None, None, {"tally": tally}, notes + [why]

    meta = {
        "defs_as_of": defs_as_of,
        "domain_status": domain_status,
        "domain_checks": domain_checks,
        "demand_status": demand.get("status"),
        "demand_source_domains": demand.get("source_domains"),
        "demand_source_freshness_check": demand.get("source_freshness_check"),
        "recipe_sections_consulted": consulted,
        "tally": tally,
    }
    return points, unresolved, meta, notes


def main():
    ap = argparse.ArgumentParser(description="Emit the PRODUCTIONS tab's as-of figures.")
    ap.add_argument("savegame_dir")
    ap.add_argument("--farm-id", type=int, default=1)
    ap.add_argument("--cache-dir", default=None,
                    help="cache/domains/ holding production_defs.json")
    ap.add_argument("--mods-dir", default=None,
                    help="mods/ dir, forwarded to read_productions.py to resolve "
                         "real store names (D4/D5) -- best-effort, matches "
                         "emit_farm_xml.py's/emit_fields_xml.py's own --mods-dir")
    ap.add_argument("--out", default=None,
                    help="full path to productions.xml (default: the modSettings bridge)")
    ap.add_argument("--profile-dir", default=None,
                    help="FarmingSimulator2025 profile dir, for the default --out")
    ap.add_argument("--fast", action="store_true",
                    help="mtime+size freshness check instead of a full re-hash")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    savegame_dir = os.path.abspath(args.savegame_dir)
    if not os.path.isdir(savegame_dir):
        print(json.dumps({"error": "no such savegame_dir: %s" % savegame_dir}))
        return 1
    savegame_key = os.path.basename(savegame_dir.rstrip("/\\"))

    cache_dir = args.cache_dir
    if cache_dir is None:
        print(json.dumps({"error": "--cache-dir is required: it names the "
                                   "cache/domains/ directory holding "
                                   "production_defs.json, and guessing one "
                                   "would read another farm's definitions"}))
        return 1

    mode = provenance.FAST if args.fast else provenance.FULL
    try:
        points, unresolved, meta, notes = collect(
            savegame_dir, args.farm_id, cache_dir, mode, mods_dir=args.mods_dir)
    except Exception as exc:                       # a parser crash is a note
        points, unresolved, meta, notes = None, None, {}, [
            "%s: %s" % (type(exc).__name__, exc)]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    written = refused = None
    xml = None

    out = args.out
    if out is None:
        profile = args.profile_dir or os.path.dirname(savegame_dir)
        out = os.path.join(profile, "modSettings", MOD_NAME, savegame_key,
                           "productions.xml")

    if points is not None:
        xml = build_xml(points, unresolved or [], savegame_key, generated_at,
                        args.farm_id, meta["defs_as_of"])
        if args.dry_run:
            print(xml)
        else:
            prior_ids, prior_readable = published_points(out)
            lost = sorted(prior_ids - {p["id"] for p in points})
            # ⛔ A DEGRADED RUN MUST NOT DESTROY A GOOD DOCUMENT, and the
            # predicate is NEITHER "notes" NOR "empty". A clean run always
            # publishes -- a player who sells a production must see it go. Only
            # a degraded run that would DROP points already published is refused.
            if notes and not prior_readable:
                refused = ("degraded run, and the document already at %s could "
                           "not be read to see what it publishes; it is kept "
                           "untouched rather than overwritten on the assumption "
                           "that it holds nothing" % out)
            elif notes and lost:
                refused = ("degraded run would have dropped published point(s) "
                           "%s; the existing document is kept and its generatedAt "
                           "left alone" % ", ".join(lost))
            else:
                atomic_write(out, xml)
                written = out
    else:
        # ⛔ NOTHING IS WRITTEN AT ALL when the collection failed. An empty
        # document carrying a fresh generatedAt is absence overwriting presence,
        # and its atomicity would make it worse rather than better.
        refused = ("nothing was collected, so no document is written and any "
                   "existing one is left exactly as it is")

    print(json.dumps({
        "written": written,
        "refused": refused,
        "savegame": savegame_key,
        "farm_id": args.farm_id,
        "generated_at": generated_at,
        "defs_as_of": (meta or {}).get("defs_as_of"),
        "points_emitted": 0 if points is None else len(points),
        "unresolved_lines": 0 if unresolved is None else len(unresolved),
        "domain_status": (meta or {}).get("domain_status"),
        "domain_checks": (meta or {}).get("domain_checks"),
        "demand_status": (meta or {}).get("demand_status"),
        "demand_source_domains": (meta or {}).get("demand_source_domains"),
        "demand_source_freshness_check": (meta or {}).get("demand_source_freshness_check"),
        "recipe_sections_consulted": (meta or {}).get("recipe_sections_consulted"),
        "tally": (meta or {}).get("tally"),
        "notes": notes,
    }, indent=2))
    return 1 if notes or points is None else 0


if __name__ == "__main__":
    sys.exit(main())
