"""
Read vehicles.xml -> owned equipment, price, fill levels, wear/damage, fuel.

Usage: python3 read_vehicles.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

CONFIRMED by running against a real save (farmId=1): <vehicle> elements
carry ownership directly as a farmId="N" attribute -- no join needed. Of 50
total <vehicle> entries in this save, 24 have farmId="1" (the player's fleet)
and 26 have farmId="0" (unowned map props -- e.g. a BNSF locomotive, its
hoppers and flatbed wagons). Filtering on farmId is required; the previous
version of this script had no ownership concept at all and reported all 50 as
if they were the player's.

price lives directly on <vehicle price="...">. This is the field a fleet
valuation needs and the prior version omitted it entirely while carrying a
full `all_attrs` dump of every other attribute (bloat, now dropped).

damage and fuel are NOT top-level attributes (the prior version looked for
`damage`/`wearTotal`/`fuelLevel`/`fuel` directly on <vehicle> and always got
None/0 -- a silent miss, not a true zero):
    - damage lives on the nested <wearable damage="..."/> child.
    - fuel lives on <fillUnit><unit fillType="DIESEL" fillLevel="..."/></fillUnit>
      (implements/trailers with no engine have no DIESEL unit -> null, correctly,
      not 0).

CARGO -- what the vehicle CARRIES, not what it IS (added 2026-07-24)
--------------------------------------------------------------------
This script used to read <fillUnit> for the DIESEL unit ONLY and throw the
rest away. That made the farm's actual PRODUCE invisible: 76,772 L of OAT and
46,934 L of CANOLA were sitting in two combines in this very save, worth
~$63.7k, and nothing in this skill could see a litre of it. A manager that
tracks what the farm owns and owes but not what it has produced is missing
the middle of the pipeline. `fill_units` now reports EVERY unit; `fuel_level`
is kept, unchanged, because other code reads it.

The real shape, read from this save (NOT assumed):
    <vehicle filename="$moddir$FS25_JohnDeereX91100EditedByStevie/seriesX9.xml">
      <fillUnit>
        <unit index="1" fillType="OAT"     fillLevel="76772.398438"/>
        <unit index="2" fillType="DIESEL"  fillLevel="1224.996704"/>
        <unit index="3" fillType="DEF"     fillLevel="80.999985"/>
      </fillUnit>

CARGO IS NOT CONSUMABLES, and conflating them would be its own absence-as-data
bug -- a combine full of diesel is not a combine full of grain. DIESEL/DEF/AIR
are what the machine runs ON; everything else is what it CARRIES. Each unit is
tagged with a `kind` so a caller can never accidentally sum a fuel tank into a
grain valuation. AIR is a brake-air reservoir (the mod's own XML calls the
2000-unit one a <brakeCompressor>), not a sellable anything.

"UNKNOWN" IS THE GAME'S OWN EMPTY-SLOT SENTINEL, AND THIS IS THE WHOLE
EMPTY-VS-UNKNOWN DISTINCTION IN ONE ATTRIBUTE. Confirmed two ways in this
save: three of the five X9s and all four Bergmann trailers carry
`fillType="UNKNOWN" fillLevel="0.000000"`, and economy.xml independently
lists `<fillType fillType="UNKNOWN"/>` with no price history at all -- it is
a real enum value meaning "nothing loaded", not a parser miss and not a crop.
So a unit reading UNKNOWN/0 is an EMPTY cargo hold: the farm has a container
and there is verifiably nothing in it. That is a real, useful answer and it
is reported as kind="empty_cargo_slot" -- distinct from a MISSING <fillUnit>
element, which is genuinely unknown and reports fill_units: null + a reason.
Three states, never collapsed:
    kind="cargo"             -- a real fill type with a real level
    kind="empty_cargo_slot"  -- a hold that exists and is confirmed empty
    fill_units: null         -- no <fillUnit> at all; we do NOT know

CAPACITY IS NOT IN vehicles.xml -- and the mod zip is why 76,772 L is real.
That number fails a plausibility check against the BASE game (a John Deere
X9 1100's real grain tank is ~14,000-16,200 L), and this codebase's own rule
says to investigate a number like that before reporting it. Investigated,
2026-07-24: it is REAL. The vehicle is not a base X9, it is
`$moddir$FS25_JohnDeereX91100EditedByStevie/seriesX9.xml`, and that mod's own
XML declares three selectable grain-tank configurations --
    fillUnitConfiguration valueDefault   -> capacity 16200
    fillUnitConfiguration valueExtension -> capacity 120000
    fillUnitConfiguration valueExtension -> capacity 240000
-- and the save records `<configuration name="fillUnit" id="3" isActive="true"/>`
on that exact vehicle. Config 3 = a 240,000 L tank, so 76,772 L is 32% of a
tank that genuinely exists. The base-game figure was the wrong yardstick;
the mod's own package is the right one (this is the same "resolve inside the
item's own package, never fall back to the base install's same-named file"
rule that read_store_prices.py exists to enforce -- F-019). Capacity is NOT
reported here: it is not in vehicles.xml, it requires opening the mod zip and
resolving the active configuration id, and that resolver lives in
read_store_prices.py. Percent-full is therefore not computed rather than
guessed.
age and operatingTime ARE top-level <vehicle> attributes and were already
correctly positioned; kept as-is.

`specializations` (added for a farm_snapshot.py capability check, F-026):
each <vehicle>'s own DIRECT CHILD tag names -- e.g. a combine harvester's
runtime state includes a <combine> element, a header/cutting attachment
includes <cutter>, a baler would include <baler>. This is real capability
signal read directly from THIS save's own data, not inferred from filenames
or model names -- confirmed against this save that name-guessing would have
been actively wrong: `$moddir$FS25_northStar1230FBEditedByStevie/...` reads
like a flatbed trailer ("FB") from its name, but its actual specialization
tag is `cutter` (a header/cutting attachment), not `trailer`. Do not infer a
vehicle's role from filename/mod name; use `specializations` instead. This
is NOT a full capability resolver (it doesn't determine fruit-type
compatibility, working width, or anything defined in the vehicle's own
store/config XML inside its mod zip -- that's a separate, deliberately
unduplicated effort, see F-019/read_store_prices.py) -- it only answers
"does this save's own runtime state say this vehicle has a <combine>/
<cutter>/<baler>/etc. specialization," which is enough to rule capability
IN or OUT for the specializations it does carry.

Output contract:
    - Never returns [] / a guess for missing data. If vehicles.xml is missing
      or unparsable, or --farm-id matches no vehicles AND the farm itself is
      unknown, this emits enough detail to tell "farm has no vehicles" apart
      from "farm-id doesn't exist" -- never a silent "0 owned, all good".
    - Reports both the owned set (primary, what a briefing should quote) and
      the total seen across the whole file (context), so an inflated
      "you own N vehicles" claim can never silently reappear.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit


def parse_farm_id_arg(argv):
    """Pull --farm-id N out of argv; default 1. Returns (farm_id, error_or_None)."""
    farm_id = 1
    args = argv[2:]  # argv[0] = script, argv[1] = savegame_dir (already consumed)
    i = 0
    while i < len(args):
        if args[i] == "--farm-id":
            if i + 1 >= len(args):
                return None, "usage: read_vehicles.py <savegame_dir> [--farm-id N] -- --farm-id given with no value"
            try:
                farm_id = int(args[i + 1])
            except ValueError:
                return None, f"--farm-id must be an integer, got {args[i + 1]!r}"
            i += 2
        else:
            i += 1
    return farm_id, None


def extract_damage(v_elem):
    wearable = v_elem.find("wearable")
    if wearable is None:
        return None
    return wearable.attrib.get("damage")


def extract_fuel(v_elem):
    fill_unit = v_elem.find("fillUnit")
    if fill_unit is None:
        return None
    for unit in fill_unit.findall("unit"):
        if unit.attrib.get("fillType") == "DIESEL":
            return unit.attrib.get("fillLevel")
    return None


# What a machine runs ON, as opposed to what it CARRIES. Confirmed present in
# this save's own vehicles.xml. Kept deliberately small and explicit: a fill
# type NOT in here is treated as cargo, so a new/modded crop is never silently
# swallowed into the consumables bucket and dropped from a valuation.
CONSUMABLE_FILL_TYPES = {"DIESEL", "DEF", "AIR", "ELECTRICCHARGE", "METHANE"}

# The game's own "nothing loaded" enum value. See the module docstring: this
# is corroborated by economy.xml carrying <fillType fillType="UNKNOWN"/> with
# no price history -- it is a sentinel, not a crop.
EMPTY_FILL_TYPE_SENTINEL = "UNKNOWN"


def classify_unit(fill_type):
    """cargo / consumable / empty_cargo_slot / indeterminate. Never guesses:
    a unit with no fillType attribute at all is 'indeterminate', which is not
    the same claim as 'empty'."""
    if fill_type is None:
        return "indeterminate"
    if fill_type == EMPTY_FILL_TYPE_SENTINEL:
        return "empty_cargo_slot"
    if fill_type in CONSUMABLE_FILL_TYPES:
        return "consumable"
    return "cargo"


def extract_fill_units(v_elem):
    """Returns (units_list_or_None, note_or_None).

    None (with a note) means "this vehicle has no <fillUnit> element" -- i.e.
    UNKNOWN, we cannot say what it holds. It never means "empty". An empty
    hold is a populated unit with kind='empty_cargo_slot'. Collapsing those
    two would be exactly the absence-looking-like-data bug this codebase is
    built to prevent.
    """
    fill_unit = v_elem.find("fillUnit")
    if fill_unit is None:
        return None, ("no <fillUnit> element on this vehicle -- its contents are UNKNOWN, "
                      "not empty. (Many implements genuinely have no fill unit at all.)")

    units = fill_unit.findall("unit")
    if not units:
        return None, ("<fillUnit> is present but has no <unit> children -- schema may differ "
                      "for this vehicle. Contents UNKNOWN, not empty.")

    out = []
    for u in units:
        fill_type = u.attrib.get("fillType")
        level_raw = u.attrib.get("fillLevel")
        try:
            level = float(level_raw) if level_raw is not None else None
        except ValueError:
            level = None
        out.append({
            "index": u.attrib.get("index"),
            "fill_type": fill_type,
            "fill_level_litres": level,
            "kind": classify_unit(fill_type),
            "level_note": None if level is not None else (
                f"fillLevel attribute missing or unparsable ({level_raw!r}) -- level UNKNOWN, not 0."
            ),
        })
    return out, None


def summarize_cargo(owned):
    """Total real cargo per fillType across the owned fleet, with where it sits.

    Returns (totals, unreadable_list).

    Only kind=='cargo' counts -- never consumables, never the UNKNOWN
    sentinel. A cargo unit whose fillLevel is 0 is genuinely empty and
    contributes nothing, which is correct.

    But a cargo unit whose fillLevel could NOT BE PARSED is a different thing
    entirely, and it does not get to quietly vanish into the same silence as
    an empty one: it is collected into `unreadable` and surfaced by the
    caller. Dropping it would be this codebase's signature bug committed by
    the very function written to fix it -- an unknown quantity of a real crop,
    summed as if it were zero, in a total that then looks complete.
    """
    totals = {}
    unreadable = []
    for v in owned:
        for u in (v.get("fill_units") or []):
            if u["kind"] != "cargo":
                continue
            litres = u.get("fill_level_litres")
            if litres is None:
                unreadable.append({
                    "unique_id": v.get("unique_id"),
                    "filename": v.get("filename"),
                    "fill_type": u.get("fill_type"),
                    "why": u.get("level_note") or "fillLevel unparsable",
                })
                continue
            if litres == 0:
                continue
            entry = totals.setdefault(u["fill_type"], {"total_litres": 0.0, "locations": []})
            entry["total_litres"] += litres
            entry["locations"].append({
                "unique_id": v.get("unique_id"),
                "filename": v.get("filename"),
                "litres": litres,
            })
    return totals, unreadable


def extract_specializations(v_elem):
    """Sorted, deduplicated direct-child tag names -- the save's own record
    of this vehicle's specializations (combine, cutter, baler, sprayer, ...).
    See the module docstring's F-026 note: this is real data, not a filename
    guess, and it's the only thing that should be used to judge capability."""
    return sorted(set(c.tag for c in v_elem))


def main():
    savegame_dir = arg_or_exit("read_vehicles.py <savegame_dir> [--farm-id N]")
    farm_id, arg_err = parse_farm_id_arg(sys.argv)
    if arg_err:
        emit({"error": arg_err})
        return

    path = os.path.join(savegame_dir, "vehicles.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({"error": generic.get("error", "unknown error reading vehicles.xml")})
        return

    all_vehicles = list(root.iter("vehicle"))
    if not all_vehicles:
        emit({
            "error": "vehicles.xml parsed but contained no <vehicle> elements -- schema may have changed.",
            "calibration_needed": True,
        })
        return

    # Check whether farmId is present at all -- if not, this schema doesn't
    # match what this script expects, and filtering would silently produce
    # a false "0 owned".
    missing_farm_id = [v for v in all_vehicles if "farmId" not in v.attrib]
    if len(missing_farm_id) == len(all_vehicles):
        emit({
            "error": "no <vehicle> element in vehicles.xml has a farmId attribute -- schema may have changed. Cannot determine ownership.",
            "calibration_needed": True,
            "total_seen": len(all_vehicles),
        })
        return

    seen_farm_ids = set()
    owned = []
    for v in all_vehicles:
        a = v.attrib
        if "farmId" not in a:
            continue
        try:
            fid = int(a["farmId"])
        except ValueError:
            continue
        seen_farm_ids.add(fid)
        if fid != farm_id:
            continue
        price_raw = a.get("price")
        fill_units, fill_units_note = extract_fill_units(v)
        owned.append({
            "unique_id": a.get("uniqueId"),
            "filename": a.get("filename"),
            "price": float(price_raw) if price_raw is not None else None,
            "age": a.get("age"),
            "operating_time": a.get("operatingTime"),
            "damage": extract_damage(v),
            # Kept for backwards compatibility -- farm_snapshot.py and others
            # read this. It is the DIESEL unit's level, i.e. a subset of
            # fill_units below; it is not the vehicle's cargo.
            "fuel_level": extract_fuel(v),
            "fill_units": fill_units,
            "fill_units_note": fill_units_note,
            "property_state": a.get("propertyState"),
            "specializations": extract_specializations(v),
        })

    if farm_id not in seen_farm_ids:
        emit({
            "error": (
                f"farm_id {farm_id} owns no vehicles AND does not appear as a farmId "
                f"on any <vehicle> in vehicles.xml. Farm ids present in this file: "
                f"{sorted(seen_farm_ids)}. This is likely an invalid --farm-id, not a "
                f"farm that genuinely owns nothing -- verify against farms.xml."
            ),
            "farm_id": farm_id,
            "farm_ids_seen": sorted(seen_farm_ids),
            "total_seen": len(all_vehicles),
            "calibration_needed": False,
        })
        return

    total_price = sum(v["price"] for v in owned if v["price"] is not None)
    cargo, cargo_unreadable = summarize_cargo(owned)
    no_fill_unit_count = sum(1 for v in owned if v["fill_units"] is None)

    emit({
        "file": path,
        "farm_id": farm_id,
        "owned_count": len(owned),
        "total_seen": len(all_vehicles),
        "farm_ids_seen": sorted(seen_farm_ids),
        "owned_total_price": total_price,
        "cargo_on_board": {
            "by_fill_type": cargo,
            "fill_types_carried": sorted(cargo),
            "state": "carrying" if cargo else ("empty" if not cargo_unreadable else "partially_unreadable"),
            "unreadable_cargo_units": cargo_unreadable,
            "totals_are_complete": not cargo_unreadable,
            "totals_are_complete_note": None if not cargo_unreadable else (
                f"{len(cargo_unreadable)} cargo unit(s) carry a real fill type but an unparsable "
                "fillLevel -- an UNKNOWN quantity of a real crop. They are listed in "
                "unreadable_cargo_units and are NOT summed into by_fill_type, so the totals "
                "above are a FLOOR, not the farm's full position. Do not quote them as complete."
            ),
            "note": (
                "Real CARGO only -- DIESEL/DEF/AIR are excluded as consumables (a combine "
                "full of fuel is not a combine full of grain), and the game's UNKNOWN "
                "empty-slot sentinel is excluded as the empty hold it is. Litres are raw "
                "fillLevel. Value them with read_fill_prices.py (economy.xml's per-period "
                "curve); do NOT use read_prices.py's meanValue, which is 0 on this "
                "never-traded farm and would price this grain at nothing."
                if cargo else
                "state='empty' is a REAL, checked answer: every owned vehicle's fill units "
                "were read and not one holds a non-consumable fill type. It does not mean "
                "the fill units were unreadable -- that case reports fill_units: null with "
                "a reason on the vehicle itself, and is counted in "
                "vehicles_with_no_fill_unit_element below."
            ),
        },
        "vehicles_with_no_fill_unit_element": no_fill_unit_count,
        "vehicles_with_no_fill_unit_element_note": (
            f"{no_fill_unit_count} of {len(owned)} owned vehicles have no readable <fillUnit> "
            "-- their contents are UNKNOWN, not empty, and they are excluded from "
            "cargo_on_board rather than counted as carrying nothing. Most are implements "
            "that genuinely have no fill unit."
        ),
        "vehicles": owned,
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
