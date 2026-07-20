"""
Read fields.xml -> per-field crop/growth/ground state, WITH ownership when it
can be resolved.

Usage: python3 read_fields.py <savegame_dir> [--farm-id N]
                             [--owned-fields LIST_OR_PATH] [--mods-dir PATH]
                             [--no-resolve]
    --farm-id N          Whose fields to mark as owned (default: 1).
    --owned-fields SPEC  Explicit override: a comma-separated list of field ids
                         ("3,7,12"), or a path to a JSON list / {"owned_field_ids":
                         [...]} / plain comma-or-newline text file. HIGHEST
                         precedence -- the player's word beats any derivation.
    --mods-dir PATH      Where the map mod lives, for ownership resolution. If
                         omitted, taken from sanctum/config.json -> paths.mods_dir.
    --no-resolve         Skip resolution entirely; every "owned" stays null.

OWNERSHIP: HOW IT IS RESOLVED, AND WHY IT USED TO BE "UNKNOWABLE"
    fields.xml entries carry NO farmId:
        <field id="1" plannedFruit="FALLOW" fruitType="SUNFLOWER" .../>
    Ownership lives one level up on farmland.xml's <farmland id="N" farmId="1"/>,
    and field ids and farmland ids are DIFFERENT id spaces (122 fields vs 149
    farmlands here). The field<->farmland relationship is SPATIAL -- it lives in
    the map's infoLayer_farmlands.grle raster, not in any XML.

    This script long reported `owned: null` for every field and called the mapping
    underivable (F-004). That was true of the XML and false of the save as a whole:
    read_farmland_areas.py now decodes the GRLE raster and resolves it, validated
    against ground truth the decode cannot fake -- its parcel-id set must equal
    farmland.xml's, its total area must equal the map's declared size, and its
    computed land cost must match farms.xml's own <fieldPurchase> to the cent.

    So this script COMPOSES that resolver (it does not reimplement it -- see
    SKILL.md). Precedence, strongest evidence first:
        1. --owned-fields          the player told us. Beats everything.
        2. read_farmland_areas.py  derived + gate-checked. ~0.6s.
        3. null                    honest unknown. NEVER a guess.

    STILL DO NOT assume field id N == farmland id N. That identity holds 122/122
    on Montana 4X and is an empirical finding for THAT MAP, not an FS25 law. It is
    read_farmland_areas.py's job to establish it per-map; if resolution fails, this
    script falls back to null and says so. A wrong ownership claim would tell the
    player they own fields they don't -- exactly the class of silent, plausible
    error this project exists to prevent.

Output contract:
    - "owned" is true/false only when resolved or overridden; otherwise null.
      Never guessed from id, position, or any heuristic.
    - "ownership" reports how it was resolved (source, derivable_from_xml,
      gates), so a caller can always tell knowledge from assumption.
    - Never returns [] when fields.xml is readable; a read failure is {"error"}.
    - calibration_needed means "could not confidently parse fields.xml", never
      "ownership is unknown" -- unknown ownership is an honest state, not a
      calibration failure.
"""
import json
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit


def parse_args(argv):
    """Returns (opts_dict, error_or_None)."""
    o = {"farm_id": 1, "owned_fields_spec": None, "mods_dir": None, "resolve": True}
    args = argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--farm-id":
            if i + 1 >= len(args):
                return None, "usage: --farm-id given with no value"
            try:
                o["farm_id"] = int(args[i + 1])
            except ValueError:
                return None, f"--farm-id must be an integer, got {args[i + 1]!r}"
            i += 2
        elif args[i] == "--owned-fields":
            if i + 1 >= len(args):
                return None, "usage: --owned-fields given with no value"
            o["owned_fields_spec"] = args[i + 1]
            i += 2
        elif args[i] == "--mods-dir":
            if i + 1 >= len(args):
                return None, "usage: --mods-dir given with no value"
            o["mods_dir"] = args[i + 1]
            i += 2
        elif args[i] == "--no-resolve":
            o["resolve"] = False
            i += 1
        else:
            i += 1
    return o, None


def find_mods_dir(explicit):
    """Locate the mods dir: the flag, else sanctum/config.json -> paths.mods_dir.
    Returns (path_or_None, how_or_reason)."""
    if explicit:
        if not os.path.isdir(explicit):
            return None, f"--mods-dir {explicit!r} is not a directory"
        return explicit, "--mods-dir flag"
    # Walk up from this script looking for a project sanctum. The skill may be
    # installed at project or personal level, so don't assume a fixed depth.
    here = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        cfg = os.path.join(here, "sanctum", "config.json")
        if os.path.isfile(cfg):
            try:
                with open(cfg) as f:
                    paths = (json.load(f).get("paths") or {})
                md = paths.get("mods_dir")
            except (OSError, json.JSONDecodeError) as e:
                return None, f"found {cfg} but could not read paths.mods_dir: {e}"
            if not md:
                return None, f"{cfg} has no paths.mods_dir"
            if not os.path.isdir(md):
                return None, f"paths.mods_dir {md!r} from config.json is not a directory"
            return md, f"sanctum/config.json -> paths.mods_dir"
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None, "no sanctum/config.json found above this script, and --mods-dir not given"


def derive_growth_states(savegame_dir, mods_dir):
    """Compose read_game_defs.py for each fruit's growth-state table.

    Returns (table_or_None, info). table maps FRUITNAME -> {ready:[..], cut:[..],
    dead:[..]}, all 1-based growthState numbers read from the game's own foliage
    XML.

    None means the table could not be built. It does NOT mean "nothing is ready":
    every consumer must treat an absent table as UNKNOWN, which is the entire
    lesson of F-001.
    """
    script = os.path.join(os.path.dirname(__file__), "read_game_defs.py")
    if not os.path.isfile(script):
        return None, {"error": "read_game_defs.py not found next to this script"}
    cmd = [sys.executable, script, savegame_dir]
    if mods_dir:
        cmd += ["--mods-dir", mods_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, {"error": f"read_game_defs.py could not be run: {e}"}
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, {"error": "read_game_defs.py produced unparseable output",
                      "stderr": (r.stderr or "")[:400]}
    if "error" in d:
        return None, {"error": f"read_game_defs.py: {d['error']}"}

    table, sources = {}, {}
    for c in d.get("seed_rates") or []:
        name = (c.get("crop") or "").upper()
        g = c.get("growth_states") or {}
        if not name or not g.get("state_names"):
            continue
        table[name] = {"ready": g.get("ready") or [], "cut": g.get("cut") or [],
                       "dead": g.get("dead") or []}
        sources[name] = c.get("resolved_from")
    if not table:
        return None, {"error": "read_game_defs.py returned no growth states for any crop"}
    return table, {"crops_with_states": len(table),
                   "source": d.get("seed_rates_source"),
                   "resolved_from": sources}


def classify_field(fruit_type, growth_state, table):
    """(crop_state, reason). crop_state is one of ready/harvested/dead/growing, or
    None when it genuinely cannot be determined.

    This reads growthState, NOT groundType. groundType is the TERRAIN TEXTURE: it
    still says HARVEST_READY on a field that was cut days ago, because the texture
    is not repainted when the crop comes off. Reading it as readiness told one farm
    to go harvest two fields it had already harvested.
    """
    if table is None:
        return None, "growth-state table unavailable -- readiness UNKNOWN, not false"
    fruit = (fruit_type or "").upper()
    if not fruit or fruit == "UNKNOWN":
        return None, "field declares no fruit type"
    states = table.get(fruit)
    if states is None:
        return None, (f"no growth states known for {fruit} -- neither the map's fruitType "
                      f"list nor data/foliage/ declares it. UNKNOWN, not 'not ready'.")
    try:
        gs = int(growth_state)
    except (TypeError, ValueError):
        return None, f"growthState {growth_state!r} is not a number"

    if gs in states["cut"]:
        return "harvested", f"growthState {gs} is a harvested/cut state for {fruit}"
    if gs in states["dead"]:
        return "dead", f"growthState {gs} is a dead/withered state for {fruit}"
    if gs in states["ready"]:
        return "ready", f"growthState {gs} is a harvest-ready state for {fruit}"
    return "growing", f"growthState {gs} is a growth stage for {fruit}"


def derive_owned_field_ids(savegame_dir, farm_id, mods_dir):
    """Compose read_farmland_areas.py -- do NOT reimplement the GRLE decode.
    Returns (set_of_ids_or_None, info_dict)."""
    script = os.path.join(os.path.dirname(__file__), "read_farmland_areas.py")
    if not os.path.isfile(script):
        return None, {"error": "read_farmland_areas.py not found next to this script"}
    cmd = [sys.executable, script, savegame_dir, mods_dir, "--farm-id", str(farm_id)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, {"error": f"read_farmland_areas.py could not be run: {e}"}
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, {"error": "read_farmland_areas.py produced unparseable output",
                      "stderr": (r.stderr or "")[:400]}
    if "error" in d:
        return None, {"error": f"read_farmland_areas.py: {d['error']}"}

    gates = d.get("gates_passed") or {}
    # A decode that fails its own gates must NOT be trusted into an ownership
    # claim -- that is the whole reason the gates exist.
    if not all(gates.get(k) for k in ("gate1_id_set_matches_savegame",
                                      "gate2_area_matches_declared_map_size")):
        return None, {"error": "read_farmland_areas.py did not pass its validation gates",
                      "gates_passed": gates}
    ids = ((d.get("owned") or {}).get("field_ids"))
    if ids is None:
        return None, {"error": "read_farmland_areas.py returned no owned.field_ids"}
    xc = d.get("field_purchase_cross_check") or {}
    return set(int(i) for i in ids), {
        "gates_passed": gates,
        "field_purchase_cross_check": xc,
        "owned_area_ha": (d.get("owned") or {}).get("total_area_ha"),
        "note": ("Derived by decoding the map's infoLayer_farmlands.grle and matching each "
                 "field's world position to a parcel. Trusted only because it passes gates a "
                 "wrong decode cannot fake: its parcel-id set equals farmland.xml's, its total "
                 "area equals the map's declared size, and its land cost matches farms.xml's "
                 "own <fieldPurchase>."),
    }


def resolve_owned_field_ids(spec):
    """spec is either a comma-separated id list or a path to a file containing
    one. Returns (set_of_ints, error_or_None)."""
    if spec is None:
        return None, None

    if os.path.isfile(spec):
        try:
            with open(spec, "r") as f:
                raw = f.read()
        except OSError as e:
            return None, f"could not read --owned-fields file {spec}: {e}"

        # Try JSON first (list, or {"owned_field_ids": [...]})
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                ids = data
            elif isinstance(data, dict) and "owned_field_ids" in data:
                ids = data["owned_field_ids"]
            else:
                return None, (
                    f"--owned-fields file {spec} is valid JSON but is neither a list "
                    f"nor an object with 'owned_field_ids'."
                )
            try:
                return set(int(x) for x in ids), None
            except (ValueError, TypeError):
                return None, f"--owned-fields file {spec} contains non-integer field ids."
        except json.JSONDecodeError:
            pass

        # Fall back to comma/newline separated plain text.
        parts = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
        try:
            return set(int(p) for p in parts), None
        except ValueError:
            return None, f"--owned-fields file {spec} could not be parsed as JSON or a comma/newline id list."

    # Not a file -- treat as inline comma-separated list.
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        return None, f"--owned-fields value {spec!r} did not parse to any field ids."
    try:
        return set(int(p) for p in parts), None
    except ValueError:
        return None, f"--owned-fields must be a comma-separated list of integers or a path to a file, got {spec!r}"


def main():
    savegame_dir = arg_or_exit(
        "read_fields.py <savegame_dir> [--farm-id N] [--owned-fields LIST_OR_PATH] "
        "[--mods-dir PATH] [--no-resolve]"
    )
    opts, arg_err = parse_args(sys.argv)
    if arg_err:
        emit({"error": arg_err})
        return
    farm_id = opts["farm_id"]

    # Ownership precedence, strongest evidence first: the player's word, then a
    # gate-checked derivation, then an honest null. Never a guess.
    ownership = {"derivable_from_xml": False}
    owned_field_ids, owned_err = resolve_owned_field_ids(opts["owned_fields_spec"])
    if owned_err:
        emit({"error": owned_err})
        return

    if owned_field_ids is not None:
        ownership.update({
            "resolved": True,
            "source": "player override (--owned-fields)",
            "note": "The player stated these directly. That outranks any derivation.",
        })
    elif not opts["resolve"]:
        ownership.update({
            "resolved": False,
            "source": "--no-resolve",
            "note": "Resolution skipped by request; every field's owned is null.",
        })
    else:
        mods_dir, how = find_mods_dir(opts["mods_dir"])
        if mods_dir is None:
            ownership.update({
                "resolved": False,
                "source": None,
                "why_unresolved": how,
                "note": ("Ownership is NOT in fields.xml (no farmId). It is derivable by "
                         "decoding the map's GRLE raster, but the mods dir could not be "
                         "located. Pass --mods-dir or set paths.mods_dir in "
                         "sanctum/config.json. Every field's owned stays null -- unknown, "
                         "not guessed."),
            })
        else:
            derived, info = derive_owned_field_ids(savegame_dir, farm_id, mods_dir)
            if derived is None:
                ownership.update({
                    "resolved": False,
                    "source": None,
                    "why_unresolved": info.get("error"),
                    "note": ("Derivation was attempted and FAILED. Every field's owned stays "
                             "null. A failed decode must never be rounded up into an "
                             "ownership claim -- that is what the gates are for."),
                })
                ownership.update({k: v for k, v in info.items() if k != "error"})
            else:
                owned_field_ids = derived
                ownership.update({
                    "resolved": True,
                    "source": f"read_farmland_areas.py (mods dir via {how})",
                })
                ownership.update(info)

    path = os.path.join(savegame_dir, "fields.xml")
    root, generic = load_xml(path)

    if root is None:
        emit({"error": generic.get("error", "unknown error reading fields.xml")})
        return

    field_elems = list(root.iter("field"))
    if not field_elems:
        emit({
            "error": "fields.xml parsed but contained no <field> elements -- schema may have changed.",
            "calibration_needed": True,
        })
        return

    growth_table, growth_info = derive_growth_states(savegame_dir, mods_dir)

    fields = []
    unresolved_override_ids = set(owned_field_ids) if owned_field_ids is not None else None

    for field_elem in field_elems:
        a = field_elem.attrib
        fid_raw = a.get("id")
        owned = None
        if owned_field_ids is not None and fid_raw is not None:
            try:
                fid_int = int(fid_raw)
                owned = fid_int in owned_field_ids
                unresolved_override_ids.discard(fid_int)
            except ValueError:
                owned = None

        crop_state, crop_state_reason = classify_field(
            a.get("fruitType"), a.get("growthState"), growth_table)

        fields.append({
            "id": fid_raw,
            "owned": owned,
            "planned_fruit": a.get("plannedFruit"),
            "fruit_type": a.get("fruitType"),
            "growth_state": a.get("growthState"),
            "last_growth_state": a.get("lastGrowthState"),
            "weed_state": a.get("weedState"),
            "stone_level": a.get("stoneLevel"),
            "ground_type": a.get("groundType"),
            "spray_type": a.get("sprayType"),
            "spray_level": a.get("sprayLevel"),
            "lime_level": a.get("limeLevel"),
            "roller_level": a.get("rollerLevel"),
            "plow_level": a.get("plowLevel"),
            "stubble_shred_level": a.get("stubbleShredLevel"),
            "water_level": a.get("waterLevel"),
            # THE field to read. ground_type above is the terrain texture and does
            # not reset when a crop is cut -- see classify_field().
            "crop_state": crop_state,
            "crop_state_reason": crop_state_reason,
        })

    owned_fields = [f for f in fields if f["owned"] is True]

    # Was: `f["ground_type"].startswith("HARVEST_READY")`. That is the TERRAIN
    # TEXTURE, and it is still HARVEST_READY on a field cut days ago -- it listed
    # two already-harvested fields as ready on this very farm (oat 71 at
    # growthState 7 = cut, canola 114 at 11 = cut). It also could not tell
    # HARVEST_READY from HARVEST_READY_OTHER, which is not a readiness
    # distinction at all: the same canola at the same growthState appears under
    # both. growthState is the fact; groundType is decoration.
    ready_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "ground_type": f["ground_type"],
         "growth_state": f["growth_state"], "weed_state": f["weed_state"]}
        for f in owned_fields if f["crop_state"] == "ready"
    ]
    harvested_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "growth_state": f["growth_state"]}
        for f in owned_fields if f["crop_state"] == "harvested"
    ]
    dead_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "growth_state": f["growth_state"]}
        for f in owned_fields if f["crop_state"] == "dead"
    ]
    unknown_state_owned = [
        {"id": f["id"], "fruit_type": f["fruit_type"], "growth_state": f["growth_state"],
         "why": f["crop_state_reason"]}
        for f in owned_fields if f["crop_state"] is None
    ]

    result = {
        "file": path,
        "farm_id": farm_id,
        "field_count": len(fields),
        "field_count_note": "Fields on the MAP. See owned_field_count for the farm's own.",
        "owned_field_count": len(owned_fields) if ownership.get("resolved") else None,
        "owned_field_ids": sorted(int(f["id"]) for f in owned_fields) if ownership.get("resolved") else None,
        # The single most decision-relevant thing this parser can say: a ripe crop
        # on ground the player actually owns. Empty list = checked and none ready.
        # null = ownership unresolved, so we genuinely do not know -- do not read
        # an absent list as "nothing to harvest".
        "harvest_ready_on_owned_land": (
            ready_owned if (ownership.get("resolved") and growth_table is not None) else None),
        "harvest_ready_note": (
            "From growthState vs the crop's own foliage states -- NOT groundType, which is "
            "the terrain texture and stays HARVEST_READY after a field is cut. Empty list "
            "means resolved and none are ready. null means ownership or the growth-state "
            "table is unresolved -- unknown, NOT 'nothing to harvest'."
        ),
        "harvested_on_owned_land": (
            harvested_owned if (ownership.get("resolved") and growth_table is not None) else None),
        "harvested_note": (
            "Fields whose crop is CUT. FS25 records no harvest timestamp anywhere, so this "
            "is a state, not an event: to date it, diff against the previous session."
        ),
        "dead_on_owned_land": (
            dead_owned if (ownership.get("resolved") and growth_table is not None) else None),
        "unknown_crop_state_on_owned_land": (
            unknown_state_owned if ownership.get("resolved") else None),
        "unknown_crop_state_note": (
            "Fields whose readiness could NOT be determined, each with a reason. These are "
            "not 'not ready' -- they are unknown, and saying so is the point."
        ),
        "growth_states": growth_info,
        "fields": fields,
        "ownership": ownership,
        "calibration_needed": False,
    }

    if owned_field_ids is not None:
        result["ownership"]["override_applied"] = True
        result["ownership"]["override_owned_field_ids"] = sorted(owned_field_ids)
        result["ownership"]["override_owned_count"] = len(owned_field_ids)
        if unresolved_override_ids:
            result["ownership"]["override_ids_not_found_in_fields_xml"] = sorted(unresolved_override_ids)
    else:
        result["ownership"]["override_applied"] = False

    emit(result)


if __name__ == "__main__":
    main()
