#!/usr/bin/env python3
"""Publish the FARM tab's as-of figures for ONE savegame.

    python3 emit_farm_xml.py <savegame_dir> [--farm-id N] [--out PATH] [--config PATH] [--dry-run]

WHAT THIS IS
------------
The mod's FARM tab renders 20 lines in 5 groups. Transport is PER-GROUP and
follows where the evidence actually is (ruled 2026-09-02):

    A money      LIVE   -- read from the engine at tab open
    D contracts  LIVE   -- read from the engine at tab open
    B land       FILE   -- this script
    C productions FILE  -- this script
    E fleet      FILE   -- this script

So this emits TWELVE values, not twenty. A and D are deliberately absent.

⛔ WHY D IS NOT HERE. A field-tied contract's reward is computed by the game at
accept-time and is NEVER WRITTEN TO THE SAVE while the contract is only offered;
read_missions.py reports it as "UNKNOWN, not zero" for exactly that reason
(FRICTION-LOG F-025 -- reporting "$0" would talk the player out of the only work
their fleet can do). There is no deadline field in the save either. Both have
real bodies in the archive, so the engine is the only place either can be known.

⛔ WHY NOT cache/domains/*.json. Two reasons, and the first is fatal. (1) Lua in
FS25 has NO file-read primitive: `io` is sandboxed to write-only, so the mod
cannot read JSON at all -- the engine XML API is the only reader it has. (2) The
eight ENVELOPE_DOMAINS carry neither land nor missions, so the cache could
supply only 3 of these 10 lines anyway. This script therefore calls the
registered parsers directly, through collect_state.run()'s existing subprocess
shape -- not a second invocation convention.

⛔ ABSENCE IS NEVER A ZERO. A parser that fails, times out or returns an error
contributes NO <value> elements, and the mod renders the word `unknown` for
those rows (guard 8, DEC-001). A blank and a zero are both absence dressed as
data; 0 vehicles and "we could not ask" are different facts.

OUTPUT (schema 1), written atomically beside cards.xml:
    modSettings/FS25_AIFarmManager25/<savegameKey>/farm.xml
    <farmManager25Farm schema="1" generatedAt="..." savegame="savegame1">
      <value id="b1" num="50"/>
      ...
      <unknown id="c2" reason="..."/>
    </farmManager25Farm>
`<unknown>` is an ADDED element, not a schema bump (see build_xml docstring):
it names WHY c2/c3 read `unknown` on the tab (and, per run, why e4 does when no
tank could be measured), for rows that are absent by design rather than
because a parser failed. FarmManager25.readFarmFile reads its PRESENCE (F7) and the
FARM tab prints the existing refusal tag for a refused figure; the reason prose itself
is never rendered.
Per-savegame, never machine-global: money, land, contracts and fleet are
properties of a SAVEGAME (BUG-027). The key is basename(savegame_dir), the same
fact FarmManager25.savegameKey() derives from missionInfo.savegameDirectory, so
the two halves cannot invent different values.
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

import collect_state  # noqa: E402  -- reuse its subprocess shape, don't reinvent
import farm_snapshot  # noqa: E402  -- F8: e4 comes from ITS fleet tiers, not a second copy

SCHEMA_VERSION = 1
MOD_NAME = "FS25_AIFarmManager25"
# The root element this script writes. published_values() refuses to count
# <value> rows out of a document carrying any other root.
ROOT_TAG = "farmManager25Farm"

# The game's OWN threshold for repair, taken from its HUD rather than invented
# here. SpeedMeterDisplay.lua:379-383 turns the repair bar red once remaining
# condition drops to 0.2, i.e. damage >= 0.8. Using the engine's own cut-off
# means the tab agrees with what the player already sees on the vehicle HUD
# instead of asserting a second opinion.
#
# ⭐ LOW FUEL IS NOT DEFINED HERE ANY MORE (F8 / BUG-039, owner ruling D-2:
# <=25%). It is `farm_snapshot.build_fleet`'s severe fuel tier -- the SAME
# function behind Cyrus's fuel alert -- so FARM and MESSAGES cannot disagree
# about what "low" means. The old 10% constant lived here beside a comment
# claiming the tab agreed with the vehicle HUD; nothing ever read it.
DAMAGE_NEEDS_REPAIR = 0.8

# The FARM tab's `unknown` rows that are DELIBERATE, not defects -- documented
# in collect_productions() (c2, c3), which points back here instead of
# restating the reason, so the two copies cannot drift. (e4 was a third until F8:
# its capacity now comes from the store-XML pass, so when it is unknown the
# reason is per-run -- see collect_fleet -- rather than a constant.) This
# dict is the SINGLE SOURCE: main() publishes these exact strings to the
# stdout JSON (`rows_unknown_by_design`) and to the XML (`<unknown reason=.../>`).
#
# ⛔ THESE MUST NEVER REACH `notes`. c2/c3 fire on EVERY HEALTHY RUN (e4 is a
# measured value since F8; its per-run unknown reason rides the same channel), and
# `notes` gates the refusal and exit-code guards in main() -- routing a
# by-design reason through `notes` would make every clean run exit 1 and
# refuse to write farm.xml at all. This is a deliberately SEPARATE channel.
ROWS_UNKNOWN_BY_DESIGN = {
    "c2": ("a percentage needs a capacity, and a building's capacity is in its "
           "own definition file, which read_building_capacity.py opens for each "
           "owned building when the manager runs it -- this publish does not open "
           "every definition file on every emit to fill one row"),
    "c3": "c3 needs the same capacities c2 does, so it is unknown for the same reason",
}


def _num(v):
    """A finite number, or None. Absence must never become 0.

    ⚠ COERCES NUMERIC STRINGS, and that is not laxity. These parsers read XML
    attributes and hand them back as the strings they are -- read_vehicles.py
    emits damage as "0.027986" and operating_time as "3745.618896". An earlier
    draft accepted only int/float and silently dropped EVERY fleet figure: the
    rows read `unknown` and nothing failed, because "absent" and "arrived as a
    string" looked identical downstream. A non-numeric string is still None.
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


def collect_land(savegame_dir, farm_id, mods_dir):
    """B1-B3 from read_farmland_areas.py.

    ⚠ B3: A DECLARED PER-PARCEL PRICE IS REPORTED AS UNKNOWN, NOT AS A FIGURE.
    `Farmland.price` is `fixedPrice` when a map declares <farmland price="...">,
    and otherwise a value updatePrice() derives from areaInHa x pricePerHa x
    priceScale (Farmland.lua:63-69; updatePrice's body is ABSENT from the
    archive). read_farmland_areas.py computes only the derived form. Verified
    for the map in play: Montana 4X declares 0 parcels with `price` and 149 with
    `priceScale`, pricePerHa=60000 -- so the reconstruction is faithful HERE.

    ⭐ THIS CAVEAT USED TO END "its figure would be silently wrong". IT NO
    LONGER DOES, and the reasoning is kept rather than deleted because a reader
    who finds land_value mysteriously absent should be able to learn that it is
    deliberate. The hole is closed AT THE PARSER (TECH-DEBT-103): a parcel
    declaring `price=` yields cost None instead of a derived float, and
    `land_value` is None when ANY owned parcel declares one. Summing the
    knowable parcels and skipping the rest would UNDER-report the total, which
    is a wrong number rather than a missing one -- the trade this project never
    makes.

    ⛔ THIS FILE NEEDS NO CHANGE, stated so it is not re-derived. The key is
    still `land_value`, and _num(None) already omits <value id="b3"> so the mod
    renders `unknown`. VERIFIED BY EXECUTION, not by reading: land_value=None
    yields {b1, b2} with b3 absent, while a real 0.0 still survives, so absence
    and zero stay distinguishable. Gated by
    test_an_unreadable_value_is_absent_not_zero, which already drives exactly
    this shape -- a second test asserting it would be duplication, not coverage.

    ⏳ TREE STATE, because a comment that is true only after a merge is the
    defect it warns about. The sensor ships with the farmland-price lane
    (feat/laneC-farmland-price-sensor); until that lands, this tree's
    read_farmland_areas.py still derives every parcel unconditionally. The two
    paragraphs above describe THE PARSER'S CONTRACT and THIS FILE'S handling of
    it -- the second is true today and after the merge alike, and this file's
    behaviour is unchanged either way.
    ⛔ Note this is NOT the forbidden getPricePerHa() route: that function
    (FarmlandManager.lua:505-507) returns the map-wide RATE and nothing else, so
    using it would discard both fixedPrice and priceScale -- which is the error
    the ban exists to prevent.
    """
    extra = [mods_dir] if mods_dir else None
    # read_farmland_areas takes mods_dir as a positional BEFORE the flags.
    out = collect_state.run("read_farmland_areas.py", savegame_dir,
                            farm_id=farm_id, extra_args=None) if not extra else \
        _run_positional("read_farmland_areas.py", savegame_dir, extra[0], farm_id)
    if not isinstance(out, dict) or "error" in out:
        return {}, _why("read_farmland_areas.py", out)
    owned = out.get("owned")
    if not isinstance(owned, dict):
        return {}, "read_farmland_areas.py returned no `owned` block"
    vals = {}
    for key, src in (("b1", "count"), ("b2", "total_area_ha"), ("b3", "land_value")):
        n = _num(owned.get(src))
        if n is not None:
            vals[key] = n
    return vals, None


def _run_positional(script, savegame_dir, mods_dir, farm_id):
    """read_farmland_areas.py is the one parser taking a second positional.

    Same shape as collect_state.run() -- same interpreter, same cwd-independent
    path, same json-or-structured-error contract -- with the extra positional
    threaded in front of the flags, which is the call shape that script's own
    usage line documents.
    """
    import subprocess
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script), savegame_dir, mods_dir]
    if farm_id is not None:
        cmd += ["--farm-id", str(farm_id)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"failed to parse output of {script}",
                "stderr": result.stderr[:2000]}


def collect_productions(savegame_dir, farm_id, mods_dir):
    """C1 from read_productions.py.

    ⚠ C2 (storage fill %) is DELIBERATELY NOT EMITTED and the row will read
    `unknown` -- see ROWS_UNKNOWN_BY_DESIGN["c2"] for why; that dict is the
    single source of the reason (main() publishes it to the JSON and XML) and
    this comment only points at it so the two copies cannot drift. Saying so
    out loud is the point: an absent row that says `unknown` is honest; a fill
    figure computed against a guessed capacity would not be.

    `mods_dir` THREADED FOR CONSISTENCY WITH collect_land ABOVE (fix round 1),
    NOT BECAUSE C1 NEEDS IT -- measured directly: `production_points.count` and
    `.status` (the only two fields this function reads) come back byte-identical
    from read_productions.py with and without a mods dir, because D4's name
    resolution touches `placeable_name` alone. So passing it here does not change
    the FARM tab today. It is still passed, matching the sibling one line above
    rather than leaving the asymmetry standing, and because a future reader of
    THIS row -- if the FARM tab ever grows a named "top production" figure --
    must not silently inherit the exact defect this whole feature exists to fix.
    """
    extra_args = ["--mods-dir", mods_dir] if mods_dir else None
    out = collect_state.run("read_productions.py", savegame_dir, farm_id=farm_id,
                            extra_args=extra_args)
    if not isinstance(out, dict) or "error" in out:
        return {}, _why("read_productions.py", out)

    sections = (out.get("sections") or {}) if isinstance(out.get("sections"), dict) else {}

    # ⛔ C1 COMES FROM THE POINT COUNT THE PARSER MEASURED, NEVER FROM THE LINE
    # ROWS. This used to build a set of placeable_ids over production_lines --
    # which counts only the points that HAPPEN TO HAVE LINES CONFIGURED. An
    # owned <productionPoint> with no <production> children emits no line row
    # and was invisible: on the owner's savegame1 the farm owns 27 points and
    # the tab rendered 23. The label promised owned production points; the code
    # delivered configured ones. One of the four missing points is a BASE-GAME
    # placeable and the trigger is ordinary play, so this was never a mod quirk.
    #
    # ⚠ COUNTING DISTINCT placeable_id VALUES IS NOT A NARROWER VERSION OF THIS
    # -- it is the defect. The rows cannot describe a point they do not contain.
    points = sections.get("production_points")
    if not isinstance(points, dict):
        return {}, "read_productions.py returned no production_points section"

    # ⛔ A REASONED ZERO IS DATA AND MUST BE PUBLISHED AS ONE (DEC-001, and the
    # sibling collectors already do it -- collect_land publishes a measured
    # b1=0, collect_fleet a measured e1=0). The parser answers
    # `unknown_by_design` with an explicit reason when a farm owns no
    # production points; the count in that case is a MEASURED 0, not an absence.
    # Returning nothing here rendered `unknown` -- making a farm that genuinely
    # owns no productions indistinguishable from a parser that crashed, which is
    # DEC-001 inverted. savegame2 and savegame3 are both in this state.
    #
    # `unavailable` and `partial` are the OPPOSITE case and must still go
    # absent: there the parser is telling us it could not measure, and a 0 would
    # be absence dressed as data.
    status = points.get("status")
    if status not in ("ok", "unknown_by_design"):
        return {}, ("read_productions.py could not measure the owned production "
                    "point count (production_points status: %r)" % (status,))

    # `count` is the section's own guarantee -- every section in this envelope
    # keeps count == len(data), so the figure cannot drift from the rows that
    # justify it.
    n = _num(points.get("count"))
    if n is None:
        return {}, "read_productions.py's production_points section carried no count"

    # C3 is unknown for the same reason as C2 -- see ROWS_UNKNOWN_BY_DESIGN["c3"].
    return {"c1": n}, None


def _run_fuel_capacity(savegame_dir, farm_id, config_path):
    """(data, error) from `read_store_prices.py --fuel-capacity`, the pass that
    resolves each vehicle's tank from its own store XML.

    ⛔ THE CONFIG IS PASSED EXPLICITLY, NEVER FOUND. `farm_snapshot.find_config`
    falls back to the working directory, and a run from the wrong directory
    degrades silently (architect V-3, measured). No `--config` -> an error here,
    which collect_fleet turns into a NOTE, never into a quiet zero."""
    if not config_path:
        return None, ("no --config was passed to emit_farm_xml.py, so the vehicles' tank "
                      "capacities cannot be resolved (the install path lives in that file)")
    return farm_snapshot.call("read_store_prices.py", savegame_dir, farm_id,
                              ["--config", config_path, "--fuel-capacity"],
                              timeout=farm_snapshot.FUEL_CAPACITY_TIMEOUT)


def _low_fuel(out, savegame_dir, farm_id, config_path):
    """(value_or_None, partial, reason_or_None, degraded_note_or_None) for e4.

    ⭐ F8 / BUG-039. The count is the number of vehicles in
    `farm_snapshot.build_fleet`'s SEVERE fuel tier (<=25%, owner ruling D-2) --
    the function behind Cyrus's own fuel alert, joined against the tank
    capacity from the store-XML pass -- so FARM and MESSAGES read one answer.

    ⛔ AN UNRESOLVED TANK IS NEVER A FULL ONE. Outcomes, kept apart:
      * NO vehicle carries a tank at all       -> 0, a measured fact (nothing can be low);
      * every fuel-carrying vehicle resolved   -> a plain count (may be 0);
      * SOME could not be (encrypted DLC, ...) -> the count of the KNOWN low
        tanks, flagged `partial` so the tab reads "N+", never "N";
      * NONE could / the resolver failed       -> no value at all.
    A resolver FAILURE (no config, script error, capacity unavailable) is a
    degraded measurement -> a note, so a run that could not measure fuel can
    never publish "Low fuel 0" and can never overwrite a real figure. Vehicles
    that carry no diesel unit (implements, pallets) are not fuel-carrying and
    are never counted as unknown."""
    cap = _run_fuel_capacity(savegame_dir, farm_id, config_path)
    data, err = cap
    if err:
        return None, False, None, "read_store_prices.py --fuel-capacity: %s" % err
    fleet = farm_snapshot.build_fleet((out, None), (data, err))
    if fleet.get("status") != "ok" or fleet.get("fuel_capacity_status") != "ok":
        return None, False, None, ("farm_snapshot.build_fleet could not tier fuel: %s"
                                   % (fleet.get("fuel_capacity_unavailable_reason")
                                      or fleet.get("reason") or "unavailable"))
    rows = fleet.get("vehicles") or []
    measured = [r for r in rows if r.get("fuel_known")]
    unresolved = fleet.get("fuel_unresolved_vehicles") or []
    if not measured and not unresolved:
        # ⭐ MEASURED ZERO, NOT AN UNKNOWN. The vehicle list was read in full (read_vehicles
        # succeeded and build_fleet tiered it) and NO engine vehicle has a resolved diesel capacity,
        # so no tank exists to be low: nothing was refused and nothing is unknown. A DRY tank
        # is NOT this case -- build_fleet reads a resolved-capacity vehicle saved with an
        # emptied UNKNOWN unit as a 0 L tank, so it is in `measured` (FM-S5-F2). Publishing this as
        # `unknown` with a reason made the tab print "Low fuel . capacity refused" -- a
        # false statement, since no capacity was ever sought (review step 5, M-1). A
        # resolver FAILURE already returned above as a note, so this can never be a
        # failure dressed as a zero.
        return 0.0, False, None, None
    if not measured:
        return None, False, (
            "no vehicle's tank could be measured (%d fuel-carrying vehicle(s) had no resolvable "
            "tank capacity or level)" % len(unresolved)), None
    low = sum(1 for r in measured if r.get("fuel_tier") == "severe")
    return float(low), bool(unresolved), (
        "%d fuel-carrying vehicle(s) had no resolvable tank capacity or level, so this is the count of "
        "the known low tanks" % len(unresolved) if unresolved else None), None


def collect_fleet(savegame_dir, farm_id, config_path=None):
    """E1, E5 and E6 (machines, pallets, bales), E2-E3, and e4 (low fuel) from the
    tank-capacity pass.

    Returns (values, note, extras) -- extras carries F8's `partial` ids and the
    per-run reason for an e4 that is `unknown`."""
    out = collect_state.run("read_vehicles.py", savegame_dir, farm_id=farm_id)
    if not isinstance(out, dict) or "error" in out:
        return {}, _why("read_vehicles.py", out), {}

    vals = {}
    owned = _num(out.get("owned_count"))

    vehicles = out.get("vehicles")
    if not isinstance(vehicles, list):
        return vals, "read_vehicles.py returned no vehicle list", {}

    # ⭐ D-3 / U10 / BUG-050: "Vehicles owned" counted PALLETS as vehicles (on the
    # farm measured, most of its "fleet"). The tab now shows THREE rows, one value each (GUARD 9): e1 Machines,
    # e5 Pallets, e6 Bales. A pallet is a vehicle with a persisted <pallet> child (D-10,
    # answered from data: all 19 encrypted-DLC pallets carry one), which read_vehicles
    # already exposes in `specializations` -- so this count needs NO store-XML pass, and
    # routing it through one would turn the DLC pallets into `unknown` (architect C-4).
    # Absence stays absence: a vehicle whose specializations could not be read makes
    # BOTH counts unknown, never a machine count that quietly includes a pallet.
    split_note = None
    if owned is not None and all(
            isinstance(v, dict) and isinstance(v.get("specializations"), list)
            for v in vehicles) and len(vehicles) == owned:
        pallets = sum(1 for v in vehicles if "pallet" in v["specializations"])
        vals["e1"] = owned - pallets
        vals["e5"] = float(pallets)
    else:
        # Never silent (review step 5, L-1): a clean run always publishes, so dropping e1/e5
        # without a note would let a previously published figure vanish unannounced.
        split_note = ("read_vehicles.py's owned_count did not match its vehicle list, or a "
                      "vehicle carried no specialisation list, so Machines and Pallets "
                      "cannot be separated")
    bales, bales_note = collect_bales(savegame_dir, farm_id, vehicles)
    if bales is not None:
        vals["e6"] = bales

    # Each figure is published only if at least one vehicle ANSWERED it. A count
    # over zero readable values is 0, and publishing that would be absence
    # dressed as data -- the F-025 shape.
    #
    # ⏳ DEFERRED, NOT MISSED -- THE PYTHON HALF OF THE PARTIAL-TOTALS ITEM.
    # saw_damage / saw_hours separate NONE-answered from SOME-answered and never
    # SOME from ALL: if 3 of 401 vehicles report operating time, e3 publishes
    # THEIR hours under a label the player reads as the fleet total. Same shape
    # as the contract rows in FarmManager25.summarizeMissions, which carries the
    # full note -- the work spans both languages and both halves must land
    # together, or the tab tells one honest story and one partial one.
    repair = hours = 0
    saw_damage = saw_hours = False
    for v in vehicles:
        if not isinstance(v, dict):
            continue
        d = _num(v.get("damage"))
        if d is not None:
            saw_damage = True
            if d >= DAMAGE_NEEDS_REPAIR:
                repair += 1
        t = _num(v.get("operating_time"))
        if t is not None:
            saw_hours = True
            hours += t
    if saw_damage:
        vals["e2"] = float(repair)
    if saw_hours:
        # ⭐ THE SAVEGAME ATTRIBUTE IS IN SECONDS, not milliseconds. The engine
        # says so in both directions: Vehicle.lua:1179 multiplies the loaded
        # value BY 1000 into its internal ms field, and :1516 divides by 1000 on
        # save. An earlier draft here divided by 3600 * 1000 and was wrong by
        # three orders of magnitude -- 1,040 hours would have rendered as 1.
        # Caught by reading the engine, not by any test I would have written.
        vals["e3"] = hours / 3600.0
    # ⭐ E4 (F8) -- see _low_fuel: the count comes from the store-XML pass, and an
    # unresolved tank is never counted as a full one.
    extras = {"partial": set(), "unknown_reasons": {}, "partial_reasons": {}}
    low, partial, reason, degraded = _low_fuel(out, savegame_dir, farm_id, config_path)
    if low is not None:
        vals["e4"] = low
        if partial:
            extras["partial"].add("e4")
            extras["partial_reasons"]["e4"] = reason
    elif reason:
        extras["unknown_reasons"]["e4"] = reason
    notes = [n for n in (degraded, bales_note, split_note) if n]
    return vals, "; ".join(notes) or None, extras


def collect_bales(savegame_dir, farm_id, vehicles):
    """E6, "Bales owned" (D-3, DEC-222) -- one value, or (None, reason).

    ⭐ WHERE FS25 PERSISTS BALES, verified against the engine's own Lua (gameSource.zip,
    2026-09-24) rather than recalled:
      * loose bales           items.xml <item className="Bale">   (read_bales_pallets b19)
      * object storage        placeables.xml <objectStorage><object className="Bale">  (b22)
      * inside a baler        vehicles.xml <baler numBales=>      (Baler.lua:797, b25)
      * on a bale loader      vehicles.xml <baleLoader><bale/>    (BaleLoader.lua:905-906)
      * in a bale wrapper     vehicles.xml <baleWrapper><bale/>   (BaleWrapper.lua:861)
    A ROUND baler keeps its bale in the fillUnit as a fill level, not a bale object
    (Baler.lua:794), so a bale being formed OR a finished one still waiting in the baler
    is not counted here; a full round baler is even saved WITHOUT numBales (:796-797)
    and counts 0. "Bales owned" therefore never includes a bale still inside a round
    baler.
    The first three come from read_bales_pallets.py (already schema-cited and tested);
    the last two are `carried_bales` on each read_vehicles.py row, the one place that
    reader does not look.

    ⛔ ZERO IS A MEASURED ANSWER HERE, NOT AN ABSENCE. items.xml is `<items/>` on every
    local save, so 0 is what this reader honestly finds -- and it is published as 0 only
    when each source says it read its container (`ok`, or `unknown_by_design`, whose
    reason is "farm_has_none"). A source that could not be read publishes NOTHING.
    """
    out = collect_state.run("read_bales_pallets.py", savegame_dir, farm_id=farm_id)
    if not isinstance(out, dict) or "error" in out:
        return None, _why("read_bales_pallets.py", out)
    sections = out.get("sections")
    if not isinstance(sections, dict):
        return None, "read_bales_pallets.py returned no sections"

    total = 0.0
    for name in ("loose_bales", "object_storage_bales"):
        sec = sections.get(name)
        n = _num(sec.get("count")) if isinstance(sec, dict) else None
        if not isinstance(sec, dict) or sec.get("status") not in ("ok", "unknown_by_design") \
                or n is None:
            return None, "read_bales_pallets.py could not measure %s" % name
        total += n
    baler = sections.get("baler_state")
    if not isinstance(baler, dict) or baler.get("status") not in ("ok", "unknown_by_design") \
            or not isinstance(baler.get("data"), list):
        return None, "read_bales_pallets.py could not measure baler_state"
    for row in baler["data"]:
        if not isinstance(row, dict):
            return None, "a baler row was unusable"
        n = _num(row.get("num_bales"))
        if n is None and _num(row.get("fill_unit_capacity")) is not None:
            # ⛔ A SAVED BALER WITH NO numBales IS ZERO BALE OBJECTS, NOT A READ FAILURE
            # (Baler.lua:791-797, gameSource.zip). numBales is written only
            # `if not spec.hasUnloadingAnimation or freeCapacity > 0`; a ROUND baler saved
            # with a FULL fill unit keeps its finished bale in the fillUnit (a fill level,
            # not a bale object) and writes fillUnitCapacity/baleTypeIndex but no numBales.
            # That is an ordinary state (a bale waiting to be dropped when the player
            # saves). Treating it as unreadable made e6 unknown, the run exit 1, and the
            # NEXT run refused -- freezing every file-backed FARM figure.
            # `fill_unit_capacity` is written unconditionally (Baler.lua:825), so its
            # presence proves a <baler> was saved; a row with neither is still a failure.
            n = 0.0
        if n is None:
            return None, "a baler's numBales could not be read"
        total += n
    for v in vehicles:
        n = _num(v.get("carried_bales")) if isinstance(v, dict) else None
        if n is None:
            return None, "read_vehicles.py gave no carried_bales for a vehicle"
        total += n
    return total, None


def _why(script, out):
    if isinstance(out, dict) and out.get("error"):
        return f"{script}: {out['error']}"
    return f"{script}: unusable output"


def build_xml(values, savegame_key, generated_at, farm_id, rows_unknown_by_design,
              partial_ids=()):
    """⛔ THE DOCUMENT IS FARM-SCOPED AND MUST SAY WHICH FARM.

    ⭐ `rows_unknown_by_design` ({id: reason}) IS AN ADDED ELEMENT, NOT A NEW
    SCHEMA. c2/c3's reasons were dying in Python comments before reaching
    the player -- this writes them as `<unknown id="c2" reason="..."/>`
    siblings of `<value>`, under the same unbumped schema. FarmManager25.lua
    walks `farmManager25Farm.value(%d)` by TAG NAME -- an `<unknown>`
    element is invisible to that loop, so a reader that does not know it is
    unaffected. (Since F7 the shipped reader has a second loop over
    `farmManager25Farm.unknown(%d)`, presence only.) `notes` (a parser FAILURE
    channel) never carries this text; see ROWS_UNKNOWN_BY_DESIGN's own
    comment for why that boundary matters.

    `farmId` used to be passed to every collector and stamped NOWHERE, while
    the only identity on the document was the savegame. The default --out path
    is savegame-keyed too, so `--farm-id 2` wrote farm 2's land, productions
    and fleet over farm 1's bridge file and readFarmFile ACCEPTED it: the one
    stamp it checks, the savegame, still matched. The tab then rendered farm 1's
    LIVE money beside farm 2's land. `--farm-id` is a documented flag
    (SKILL.md:118), so this is reachable by ordinary operator error, not by
    misuse.

    ⚠ SCHEMA IS DELIBERATELY NOT BUMPED. FarmManager25.lua refuses a document
    stamped anything but schema 1, so bumping it would make every shipped mod
    reject the file -- turning a mislabelling bug into a total outage on the
    owner's live farm. An ADDED attribute is backward compatible: the current
    reader ignores it, and a reader that learns to check it gains a real gate.

    ⛔ THE CONSUMER HALF IS NOT WRITTEN HERE. FarmManager25.lua is another
    lane's file. The check it needs is the exact shape of the existing savegame
    check at :1988 -- read `farmManager25Farm#farmId`, compare against the farm
    the session is actually playing, and discard on mismatch the way a wrong
    savegame stamp is already discarded. Until that lands this stamp is
    evidence, not enforcement, and it is stated plainly so no one reads it as a
    fix that is already closed.
    """
    # ⭐ F8: `partial="true"` marks a count that is a LOWER BOUND ("at least N"),
    # because some vehicles could not be measured. An ADDED attribute on an
    # existing element, so the shipped reader (which reads `num` only) still
    # gets the number; a reader that learns the attribute renders "N+".
    value_rows = "".join(
        '\n  <value id={} num={}{}/>'.format(
            quoteattr(k), quoteattr(repr(round(v, 4))),
            ' partial="true"' if k in partial_ids else "")
        for k, v in sorted(values.items())
    )
    unknown_rows = "".join(
        '\n  <unknown id={} reason={}/>'.format(quoteattr(k), quoteattr(v))
        for k, v in sorted(rows_unknown_by_design.items())
    )
    rows = value_rows + unknown_rows
    return (
        '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        '<farmManager25Farm schema={} generatedAt={} savegame={} farmId={}>{}\n'
        '</farmManager25Farm>\n'
    ).format(quoteattr(str(SCHEMA_VERSION)), quoteattr(generated_at),
             quoteattr(savegame_key), quoteattr(str(farm_id)), rows)


def published_values(path):
    """Which <value> ids the document ALREADY on disk publishes, and whether it
    could be READ at all. Returns (ids, readable).

    ⛔ THE IDS, NOT A COUNT. The guard below used to compare `len(values) <
    prior`, which is a CARDINALITY check standing in for a containment one. A
    degraded run that LOSES rows in one group while GAINING them in another
    passes it and overwrites: the land parser errors, b1/b2/b3 are destroyed,
    and because the totals happened to stay equal the guard never fired and
    `refused` was None. Rows are not fungible -- losing the whole land group is
    not paid for by gaining a production row.

    ⚠ `readable` SEPARATES TWO CASES THE OLD CODE COLLAPSED. A bare
    `except Exception: return 0` reported "nothing to protect" for a
    PermissionError on a present, complete, perfectly current document -- and
    that licensed a full overwrite by a degraded run. Not being able to READ a
    document is not evidence that it holds nothing.

    A MISSING file and an UNPARSEABLE one both yield an empty set with
    readable=True, and the two reasons are different but the answer is the
    same: there is genuinely nothing there yet, or what is there is corrupt and
    a run that can repair the bridge must never be wedged out by the corruption
    itself.

    ⚠ THE ROOT TAG IS CHECKED. findall("value") under ANY root counted rows out
    of a document this script did not write -- a foreign or half-migrated file
    at the bridge path would have "protected" itself with rows whose ids mean
    nothing here.
    """
    try:
        with open(path, encoding="utf-8") as f:
            root = ET.parse(f).getroot()
    except FileNotFoundError:
        return set(), True
    except ET.ParseError:
        return set(), True
    except OSError:
        # Present but unreadable. We cannot see what it holds, so we must not
        # assume it holds nothing.
        return set(), False
    if root.tag != ROOT_TAG:
        return set(), True
    return {v.get("id") for v in root.findall("value") if v.get("id")}, True


def atomic_write(path, text):
    """Write-then-rename. The mod polls this file; a reader must never catch a
    half-written one and conclude the farm has no land."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".farm-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main():
    ap = argparse.ArgumentParser(description="Emit the FARM tab's as-of values.")
    ap.add_argument("savegame_dir")
    ap.add_argument("--farm-id", type=int, default=1)
    ap.add_argument("--mods-dir", default=None,
                    help="needed by read_farmland_areas.py to resolve the map")
    ap.add_argument("--out", default=None,
                    help="full path to farm.xml (default: the modSettings bridge)")
    ap.add_argument("--profile-dir", default=None,
                    help="FarmingSimulator2025 profile dir, for the default --out")
    ap.add_argument("--config", default=None,
                    help="sanctum/config.json (its paths block holds the game install), "
                         "needed to resolve vehicles' tank capacities for the low-fuel row. "
                         "Passed explicitly, never found from the working directory.")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    savegame_dir = os.path.abspath(args.savegame_dir)
    if not os.path.isdir(savegame_dir):
        print(json.dumps({"error": f"no such savegame_dir: {savegame_dir}"}))
        return 1
    savegame_key = os.path.basename(savegame_dir.rstrip("/\\"))

    values, notes = {}, []
    partial_ids, unknown_reasons, partial_reasons = set(), {}, {}
    for collect in (
        lambda: collect_land(savegame_dir, args.farm_id, args.mods_dir),
        lambda: collect_productions(savegame_dir, args.farm_id, args.mods_dir),
        lambda: collect_fleet(savegame_dir, args.farm_id, args.config),
    ):
        try:
            res = collect()
            got, why = res[0], res[1]
            extras = res[2] if len(res) > 2 else {}
        except Exception as exc:                      # a parser crash is a note
            got, why, extras = {}, f"{type(exc).__name__}: {exc}", {}
        values.update(got)
        partial_ids |= set(extras.get("partial", ()))
        unknown_reasons.update(extras.get("unknown_reasons", {}))
        partial_reasons.update(extras.get("partial_reasons", {}))
        if why:
            notes.append(why)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Filtered by `values` rather than published as the whole constant: a row
    # that ever DOES get published (a future capacity source lands) must stop
    # being announced as unknown-by-design in the same document that carries
    # its number.
    rows_unknown_by_design = {
        k: v for k, v in ROWS_UNKNOWN_BY_DESIGN.items() if k not in values}
    # F8: a row that is unknown THIS RUN for a per-run reason (not a constant)
    # is published through the same non-note channel.
    rows_unknown_by_design.update(
        {k: v for k, v in unknown_reasons.items() if k not in values})
    xml = build_xml(values, savegame_key, generated_at, args.farm_id,
                    rows_unknown_by_design, partial_ids)

    out = args.out
    if out is None:
        profile = args.profile_dir or os.path.dirname(savegame_dir)
        out = os.path.join(profile, "modSettings", MOD_NAME, savegame_key, "farm.xml")

    # ⛔ A DEGRADED RUN MUST NOT DESTROY A GOOD DOCUMENT. atomic_write used to be
    # unconditional and `notes` only reached the exit code AFTER it, so a run in
    # which every parser failed replaced a complete farm.xml with an EMPTY one
    # carrying a FRESHER generatedAt. readFarmFile then accepted that as a valid
    # current publication -- indistinguishable from a farm that legitimately owns
    # nothing. That is absence overwriting presence, this project's founding
    # defect class, and the atomicity of the write made it worse rather than
    # better: the replacement was clean and complete.
    #
    # ⚠ THE PREDICATE IS NOT "notes" AND NOT "empty". A degraded run can still
    # carry real data worth publishing, and a farm that genuinely owns no
    # production points legitimately yields no c1 WITH NO NOTE at all -- so
    # neither signal alone separates the two. What is never right is publishing
    # FEWER rows than are already there BECAUSE something broke. A clean run
    # always publishes: a player who sells a production must see the count fall.
    written = None
    refused = None
    if args.dry_run:
        print(xml)
    else:
        prior_ids, prior_readable = published_values(out)
        # ⭐ THE NARROW CLAIM THIS GUARD MUST KEEP: A CLEAN RUN ALWAYS PUBLISHES.
        # `notes` gates every refusal below, so a player who sells a production
        # still sees the count fall. Only a DEGRADED run can ever be refused.
        lost = sorted(prior_ids - set(values))
        if notes and not prior_readable:
            refused = (
                "degraded run, and the document already at {} could not be read "
                "to see what it publishes; it is kept untouched rather than "
                "overwritten on the assumption that it holds nothing"
            ).format(out)
        elif notes and lost:
            refused = (
                "degraded run would have dropped published value(s) {}; the "
                "existing document is kept and its generatedAt left alone"
            ).format(", ".join(lost))
        else:
            atomic_write(out, xml)
            written = out

    # ⛔ The RESULT is the document, not this summary -- but a caller that cannot
    # see which rows are missing cannot tell a quiet parser failure from a farm
    # that genuinely owns nothing. So say both, in band.
    print(json.dumps({
        "written": written,
        "refused": refused,
        "savegame": savegame_key,
        "farm_id": args.farm_id,
        "generated_at": generated_at,
        "values_emitted": sorted(values),
        "values_partial": sorted(partial_ids),
        "partial_reasons": partial_reasons,
        "rows_unknown": sorted(
            set(["b1", "b2", "b3", "c1", "c2", "c3", "e1", "e2", "e3", "e4", "e5", "e6"])
            - set(values)),
        # ⛔ NEVER `notes`. This is the reason c2/c3 (and e4, when unmeasured) explain themselves
        # WITHOUT arming the refusal/exit-code guards on every healthy run --
        # see ROWS_UNKNOWN_BY_DESIGN's own comment for the landmine this
        # avoids.
        "rows_unknown_by_design": rows_unknown_by_design,
        "notes": notes,
    }, indent=2))
    # A parser that failed is a degraded measurement and is reported as one.
    return 1 if notes else 0


if __name__ == "__main__":
    sys.exit(main())
