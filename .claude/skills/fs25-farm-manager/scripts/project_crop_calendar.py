"""
project_crop_calendar.py -- planting windows per crop, and ready / dead dates per
owned field, projected from the game's own crop files.

Usage: python3 project_crop_calendar.py <savegame_dir> [--farm-id N]
                                        [--config PATH] [--install-dir DIR]
                                        [--mods-dir DIR] [--owned-fields 1,2,3]

WHY THIS EXISTS (FM-1001 item 8, friction F-505/F-509). In the owner's test the
manager hand-wrote two scratch scripts from the map zip and the base foliage
files to build the field plan, and its first version gave no ready date for
potato and sugarbeet: it read readiness only from `isHarvestReady`, and potato's
flag sits on `cutHaulm`, a state growth never reaches. One reviewed script now
does that work, so a plan is never built from a script of the manager's own.

WHAT IT READS (map first, base game second, F-019 -- never a basename search):
  each crop's foliage XML: the FIRST <foliageLayer>'s <foliageState> elements in
  document order are the growth states, 1-based (FruitTypeDesc.lua:283-319 reads
  `foliageKey .. ".foliageState"`, foliageKey being the first layer; a second
  layer such as potato's haulm layer is NOT part of the state list) and
  <growth><seasonal> -- twelve <period>s, each with `plantingAllowed` and
  <update startState endState> rows naming states by NAME.
  environment.xml: currentDay, daysPerPeriod.  careerSavegame.xml: mapId,
  growthMode.  fields.xml: fruitType and growthState per field.

THE MODEL, AND WHAT IT CANNOT PROVE. The growth tick itself is native code:
`loadGrowth`, `getIsPlantableInPeriod` and what `growthMode` means are not in
the readable engine source (gameSource.zip), and nothing in a save says whether a
period's update rows fire when that period STARTS or when it ENDS (tested on
2026-10-01: `lastGrowthState` is the last step taken, not the last tick, so it
cannot settle it). So this script never states one exact day. It simulates under
BOTH readings and reports a WINDOW:
    from_day  the earlier of the two readings
    by_day    the later of the two
  reading A: a period's rows fire on its first day;
  reading B: a period's rows fire when the NEXT period begins.
With daysPerPeriod 1 that is a one-day spread. Also assumed, and stated in the
output: one update row per tick (no cascade within a tick, an update starting at
a state the field is not in does nothing), a crop is sown at state 1, the
seasonal block governs (the meaning of the save's growthMode value is native),
and nothing outside the growth block (disaster, weather, harvest) intervenes.
Days are the game's `currentDay` counter; period = ((day-1)//daysPerPeriod)%12,
the formula read_fill_prices.py confirmed against live economy.xml writes.

READY, DEAD, AND THE POTATO CASE (F-505):
  * ready_to_harvest: first day growth reaches a state flagged isHarvestReady.
  * Where isHarvestReady is only on a state growth never reaches (potato's
    cutHaulm) but a state flagged isPreparable IS reached, the crop becomes
    PREPARABLE: the player's haulm cut makes it harvestable, and that is not a
    calendar event. The output says `needs_player_step`, gives the preparable
    window and the death window, and gives NO ready day.
  * dies: first day growth reaches an isWithered state.
  * Anything not worked out is `unknown` with the reason -- never a guessed day.

Output: one JSON document. Could-not-run (bad args, no environment.xml, map zip
missing, no crop list) -> {"error": ...}, exit 1.
READ-ONLY.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit
from read_store_prices import load_paths
from read_game_defs import PackageResolver, read_map_id
from read_fill_prices import PERIODS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USAGE = ("project_crop_calendar.py <savegame_dir> [--farm-id N] [--config PATH] "
         "[--install-dir DIR] [--mods-dir DIR] [--owned-fields 1,2,3]")

# Two years of ticks. A date not reached inside this is `unknown`, not a far date.
HORIZON_TICKS = 24
SOWN_STATE = 1  # see the module docstring: stated, not proven
# Set once per run from reading_evidence(); "A", "B" or None (no evidence).
LIKELY_READING = None

# careerSavegame.xml <growthMode> as the game's own log names it ("Savegame Setting
# 'growthMode': ..."). Paired 2026-10-01 from the owner's logs and the saves' own
# files: the Riverbend save loaded as SEASONAL carried <growthMode>1 in the backups
# written in that session; savegame 1, loaded as DAILY, carries 2. Only mode 1 is shown
# to follow the crops' <seasonal> table; a value not in this map has no known name.
GROWTH_MODE_NAMES = {"1": "SEASONAL", "2": "DAILY"}
SEASONAL_MODE = "1"

READINGS = {
    "A": "a period's update rows fire on its first day",
    "B": "a period's update rows fire when the next period begins",
}


def fail(message, **extra):
    out = {"error": message}
    out.update(extra)
    emit(out)
    sys.exit(1)


def parse_args(argv):
    args = argv[1:]
    savegame_dir, farm_id = None, 1
    config = install_dir = mods_dir = owned_spec = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--farm-id", "--config", "--install-dir", "--mods-dir", "--owned-fields"):
            if i + 1 >= len(args):
                fail(f"{a} needs a value. Usage: {USAGE}")
            val = args[i + 1]
            if a == "--farm-id":
                try:
                    farm_id = int(val)
                except ValueError:
                    fail(f"--farm-id must be an integer, got {val!r}")
            elif a == "--config":
                config = val
            elif a == "--install-dir":
                install_dir = val
            elif a == "--mods-dir":
                mods_dir = val
            else:
                owned_spec = val
            i += 2
        elif a.startswith("--"):
            fail(f"unknown option {a!r}. Usage: {USAGE}")
        elif savegame_dir is None:
            savegame_dir = a
            i += 1
        else:
            fail(f"unexpected argument {a!r}. Usage: {USAGE}")
    if savegame_dir is None:
        fail(f"missing <savegame_dir>. Usage: {USAGE}")
    return savegame_dir, farm_id, config, install_dir, mods_dir, owned_spec


# ---------------------------------------------------------------------------
# Crop definitions
# ---------------------------------------------------------------------------

def _flag(el, attr):
    return (el.attrib.get(attr) or "").strip().lower() == "true"


def parse_crop(froot):
    """(crop_dict, None) or (None, reason). The growth states are the FIRST
    foliageLayer's foliageState elements in document order."""
    node = froot.find("fruitType")
    if node is None or not node.attrib.get("name"):
        return None, "the file has no <fruitType name=>"
    layer = froot.find("foliageLayer")
    if layer is None:
        return None, "the file has no <foliageLayer>, so it declares no growth states"
    elements = layer.findall("foliageState")
    names = [e.attrib.get("name") for e in elements]
    if not names or any(not n for n in names):
        return None, "a <foliageState> in the first <foliageLayer> has no name"
    if len(set(names)) != len(names):
        return None, "two growth states share a name, so an <update> cannot name one"
    flags = {k: [i for i, e in enumerate(elements, 1) if _flag(e, attr)]
             for k, attr in (("ready", "isHarvestReady"), ("preparable", "isPreparable"),
                             ("prepared", "isPrepared"), ("withered", "isWithered"),
                             ("cut", "isCut"))}
    crop = {"name": node.attrib["name"], "state_names": names, **flags,
            "periods": None, "seasonal_error": None}
    seasonal = froot.find("growth/seasonal")
    if seasonal is None:
        crop["seasonal_error"] = ("the file has no <growth><seasonal> block: no planting "
                                  "period or growth step can be read for it")
        return crop, None
    periods, seen_dupe = {}, None
    for p in seasonal.findall("period"):
        pname = p.attrib.get("name")
        rows = []
        for u in p.findall("update"):
            s, t = u.attrib.get("startState"), u.attrib.get("endState")
            if s not in names or t not in names:
                crop["seasonal_error"] = (f"period {pname} has an <update> naming a state "
                                          f"this crop does not declare ({s!r} -> {t!r})")
                return crop, None
            rows.append((names.index(s) + 1, names.index(t) + 1))
        starts = [r[0] for r in rows]
        if len(starts) != len(set(starts)):
            seen_dupe = pname
        periods[pname] = {"planting_allowed": _flag(p, "plantingAllowed"), "rows": rows}
    missing = [n for n in PERIODS if n not in periods]
    if missing:
        crop["seasonal_error"] = f"the seasonal block has no <period> for {', '.join(missing)}"
        return crop, None
    if seen_dupe:
        crop["seasonal_error"] = (f"period {seen_dupe} has two <update> rows from the same "
                                  f"state; which one the engine applies is not readable")
        return crop, None
    crop["periods"] = periods
    return crop, None


def _stem(filename):
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return (base[:-4] if base.lower().endswith(".xml") else base).lower()


def _fruit_entries(resolver, root, origin):
    """[(filename, origin)] from a map config (or a fruitTypes list file): every
    <fruitTypes> element may carry fruitType children inline AND/OR point at a list file
    with its own `filename` (XMLUtil.loadDataFromMapXML reads both). Returns
    (entries, error_or_None)."""
    entries = []
    for block in root.iter("fruitTypes"):
        for ft in block.findall("fruitType"):
            if ft.attrib.get("filename"):
                entries.append((ft.attrib["filename"], origin))
        listing = block.attrib.get("filename")
        if listing:
            lroot, _src, err = resolver.read_referenced(listing)
            if lroot is None:
                return entries, f"fruit list {listing!r} could not be read: {err}"
            for ft in lroot.iter("fruitType"):
                if ft.attrib.get("filename"):
                    entries.append((ft.attrib["filename"], f"{origin} -> {listing}"))
    return entries, None


def _base_map_config(install_dir, map_id):
    """The base game map's own config for a base-map save, or None."""
    maps = os.path.join(install_dir, "data", "maps")
    want = (map_id or "").lower()
    if not os.path.isdir(maps) or not want:
        return None
    for d in sorted(os.listdir(maps)):
        path = os.path.join(maps, d, d + ".xml")
        if d.lower() == want and os.path.isfile(path):
            return path
    return None


def load_crops(resolver, install_dir, map_id=None):
    """({NAME: crop}, [unresolved], source_label, error).

    The ENGINE's order (FruitTypeManager.lua:107-121): the map's own <fruitTypes>
    entries are loaded first, then the game's default list `data/maps/maps_fruitTypes.xml`;
    a default entry whose name a map entry already holds is dropped in favour of the map's
    (FruitTypeManager.lua:228-241). So the crop set is the default list plus the map's, and
    the map wins a name. A map crop file that will not parse is reported and its default
    namesake is NOT substituted."""
    map_entries, labels = [], []
    if resolver._zip is not None:
        from read_game_defs import _map_config_root
        mroot, cfg, err = _map_config_root(resolver, map_id)
        if mroot is None:
            return None, None, f"map:{cfg}", (err or "the map's own config could not be located")
        map_entries, err = _fruit_entries(resolver, mroot, f"map:{cfg}")
        if err:
            return None, None, f"map:{cfg}", err
        labels.append(f"map:{cfg}")
    else:
        cfg = _base_map_config(install_dir, map_id)
        if cfg:
            mroot, _g = load_xml(cfg)
            if mroot is not None:
                map_entries, err = _fruit_entries(resolver, mroot, "base-map:" + os.path.basename(cfg))
                if err:
                    return None, None, f"base-map:{cfg}", err
                labels.append("base-map:" + os.path.basename(cfg))
    base_root, err = resolver.read_base_xml(os.path.join("maps", "maps_fruitTypes.xml"))
    if base_root is None:
        return None, None, "base:data/maps/maps_fruitTypes.xml", err
    base_entries, err = _fruit_entries(resolver, base_root, "base:data/maps/maps_fruitTypes.xml")
    if err:
        return None, None, "base:data/maps/maps_fruitTypes.xml", err
    labels.append("base:data/maps/maps_fruitTypes.xml")
    source = " + ".join(labels)

    crops, unresolved, failed_stems = {}, [], set()
    for fn, origin in map_entries + base_entries:
        is_map = (fn, origin) in map_entries
        if not is_map and _stem(fn) in failed_stems:
            unresolved.append({"source_file": fn, "reason": (
                "not used: the map's own file of the same name could not be read, and the "
                "game's default is not substituted for it")})
            continue
        froot, resolved_from, ferr = resolver.read_referenced(fn)
        if froot is None:
            unresolved.append({"source_file": fn, "reason": ferr})
            if is_map:
                failed_stems.add(_stem(fn))
            continue
        crop, reason = parse_crop(froot)
        if crop is None:
            unresolved.append({"source_file": fn, "reason": reason})
            if is_map:
                failed_stems.add(_stem(fn))
            continue
        key = crop["name"].upper()
        if key in crops:
            continue  # the map's entry was loaded first and wins the name
        crop.update(source_file=fn, resolved_from=resolved_from, listed_in=origin)
        crops[key] = crop
    # A crop the player grows can be in neither list (onion): sweep the base foliage
    # folder, labelled as found by convention. Never for a name a list already holds or
    # whose file a list named and failed to read.
    foliage = os.path.join(install_dir or "", "data", "foliage")
    if install_dir and os.path.isdir(foliage):
        for d in sorted(os.listdir(foliage)):
            path = os.path.join(foliage, d, d + ".xml")
            if not os.path.isfile(path) or d.lower() in failed_stems:
                continue
            froot, _generic = load_xml(path)
            if froot is None:
                continue
            crop, _reason = parse_crop(froot)
            if crop is None or crop["name"].upper() in crops:
                continue
            crop.update(source_file=f"data/foliage/{d}/{d}.xml",
                        resolved_from="base:foliage-scan", listed_in="foliage folder scan")
            crops[crop["name"].upper()] = crop
    return crops, unresolved, source, None


# ---------------------------------------------------------------------------
# Calendar and simulation
# ---------------------------------------------------------------------------

def read_calendar(savegame_dir):
    root, generic = load_xml(os.path.join(savegame_dir, "environment.xml"))
    if root is None:
        fail(f"could not read environment.xml: {generic.get('error')}")
    try:
        day = int(root.find("currentDay").text.strip())
        dpp = int(root.find("daysPerPeriod").text.strip())
    except (AttributeError, ValueError):
        fail("environment.xml has no integer <currentDay> and <daysPerPeriod>")
    if dpp <= 0 or day < 1:
        fail(f"environment.xml gives currentDay {day}, daysPerPeriod {dpp}: not a usable calendar")
    return day, dpp


def simulate(crop, state, base_idx, base_start, dpp, reading):
    """First day each state class is reached, stepping tick by tick.
    Tick k (k >= 1) happens on day base_start + k*dpp. Reading A applies the rows
    of period base_idx+k there; reading B applies those of period base_idx+k-1.
    Returns {"ready": day|None, "preparable": day|None, "withered": day|None}
    where a class the starting state is already in counts as day base_start."""
    hit = {"ready": None, "preparable": None, "withered": None}

    def mark(s, day):
        for key in hit:
            if hit[key] is None and s in crop[key]:
                hit[key] = day

    mark(state, base_start)
    for k in range(1, HORIZON_TICKS + 1):
        idx = (base_idx + k) % 12 if reading == "A" else (base_idx + k - 1) % 12
        for src, dst in crop["periods"][PERIODS[idx]]["rows"]:
            if src == state:
                state = dst
                break
        mark(state, base_start + k * dpp)
        if all(v is not None for v in hit.values()):
            break
    return hit


def _which(a, b, pick):
    """Which reading(s) a bound comes from: "A", "B", or "A,B" when they agree."""
    day = pick(a, b)
    return ",".join(r for r, d in (("A", a), ("B", b)) if d == day)


def _likely(a, b):
    return {"A": a, "B": b}.get(LIKELY_READING)


def window(a, b, what):
    """From reading A's and reading B's day -> {"status", "from_day", "by_day",
    "likely_day", ...}. likely_day is the likely reading's (see reading_evidence())."""
    if a is None and b is None:
        return {"status": "unknown", "from_day": None, "by_day": None, "likely_day": None,
                "reason": (f"{what} is not reached within {HORIZON_TICKS} periods under "
                           f"either reading of the update timing")}
    if a is None or b is None:
        return {"status": "partial", "from_day": a if a is not None else b,
                "by_day": None, "likely_day": _likely(a, b),
                "from_day_reading": "A" if a is not None else "B", "likely_day_reading": LIKELY_READING,
                "reason": (f"{what} is reached under only one reading of the update timing "
                           f"inside {HORIZON_TICKS} periods, so no latest day is given")}
    return {"status": "projected", "from_day": min(a, b), "by_day": max(a, b),
            "from_day_reading": _which(a, b, min), "by_day_reading": _which(a, b, max),
            "likely_day": _likely(a, b), "likely_day_reading": LIKELY_READING}


def project_state(crop, state, base_idx, base_start, dpp):
    sims = {r: simulate(crop, state, base_idx, base_start, dpp, r) for r in READINGS}

    def both(key):
        return sims["A"][key], sims["B"][key]

    out = {}
    ready = window(*both("ready"), "a harvest-ready state")
    prep = window(*both("preparable"), "a preparable state")
    dies = window(*both("withered"), "a withered state")
    if ready["status"] != "unknown":
        out["ready_to_harvest"] = ready
    elif crop["ready"] and prep["status"] != "unknown":
        prep["status"] = "needs_player_step"
        prep["reason"] = (
            "isHarvestReady sits on state "
            + ", ".join(crop["state_names"][i - 1] for i in crop["ready"])
            + ", which growth never reaches; the crop becomes harvestable only after the "
              "player prepares it (the state flagged isPreparable is reached in this window). "
              "No ready day is given: the preparation is not a calendar event.")
        out["ready_to_harvest"] = {"status": "needs_player_step", "from_day": None,
                                   "by_day": None, "likely_day": None,
                                   "reason": prep["reason"]}
        out["preparable"] = {k: v for k, v in prep.items() if k != "reason"}
        out["preparable"]["status"] = "projected" if prep["by_day"] is not None else "partial"
    else:
        ready["reason"] = ready.get("reason") or "no harvest-ready state is reachable"
        out["ready_to_harvest"] = ready
    if crop["withered"]:
        if dies["status"] == "projected" and dies["from_day"] is not None:
            dies["alive_through_day"] = dies["from_day"] - 1
        out["dies"] = dies
    else:
        out["dies"] = {"status": "unknown", "from_day": None, "by_day": None,
                       "likely_day": None, "reason": "this crop declares no isWithered state, so no death day exists to project"}
    return out


def reading_evidence(crops):
    """Which reading the game's own data favours, counted afresh every run.
    A crop may be planted in a period flagged plantingAllowed. A crop sown in such a
    period starts at state 1; if the rows that govern its next tick have no row
    from state 1, it would sit unseen until the same period a year later. Count the
    plantable (crop, period) pairs where the sown crop DOES advance on its next
    tick under each reading. A designed game should advance in (nearly) all of them.
    Evidence about the design, not a measurement of the engine."""
    total = adv_a = adv_b = 0
    for c in crops.values():
        if c["periods"] is None:
            continue
        for i, name in enumerate(PERIODS):
            if not c["periods"][name]["planting_allowed"]:
                continue
            total += 1
            rows_b = c["periods"][name]["rows"]
            rows_a = c["periods"][PERIODS[(i + 1) % 12]]["rows"]
            adv_a += any(src == SOWN_STATE for src, _d in rows_a)
            adv_b += any(src == SOWN_STATE for src, _d in rows_b)
    return {
        "plantable_crop_period_pairs": total,
        "sown_crop_advances_on_next_tick_under_reading_A": adv_a,
        "sown_crop_advances_on_next_tick_under_reading_B": adv_b,
        "likely_reading": ("B" if total and adv_b > adv_a else "A" if total and adv_a > adv_b
                           else None),
        "note": ("counted from the crop files read in this run. likely_day in every window "
                 "is the likely reading's day; it is the game's design that favours it, not "
                 "a measurement of the engine, so from_day..by_day stays the honest range."),
    }


def plant_windows(crop, cur_day, cur_idx, cur_start, dpp):
    allowed = [(i, n) for i, n in enumerate(PERIODS) if crop["periods"][n]["planting_allowed"]]
    rows = []
    sown_state_has_rows = any(src == SOWN_STATE for n2 in PERIODS
                              for src, _dst in crop["periods"][n2]["rows"])
    for idx, name in allowed:
        k = (idx - cur_idx) % 12
        start = cur_start + k * dpp
        first, last = (cur_day if k == 0 else start), start + dpp - 1
        row = {"period": name, "next_window_days": [first, last], "plantable_now": k == 0}
        if sown_state_has_rows:
            row["if_planted"] = project_state(crop, SOWN_STATE, idx, start, dpp)
        else:
            row["if_planted"] = {"status": "unknown",
                                 "reason": f"no period's update rows start from state {SOWN_STATE}"}
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Fields and ownership
# ---------------------------------------------------------------------------

def owned_ids(savegame_dir, farm_id, config, mods_dir, spec):
    """(set_or_None, info). `spec` wins; otherwise read_fields.py resolves it."""
    if spec:
        ids = {s.strip() for s in spec.split(",") if s.strip()}
        return ids, {"resolved": True, "source": "--owned-fields"}
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "read_fields.py"), savegame_dir,
           "--farm-id", str(farm_id)]
    if config:
        cmd += ["--config", config]
    if mods_dir:
        cmd += ["--mods-dir", mods_dir]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        doc = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        return None, {"resolved": False, "reason": f"read_fields.py did not produce a document: {e}"}
    if doc.get("error"):
        return None, {"resolved": False, "reason": f"read_fields.py: {doc['error']}"}
    ids = doc.get("owned_field_ids")
    if not isinstance(ids, list):
        return None, {"resolved": False, "reason": "read_fields.py named no owned_field_ids"}
    return {str(i) for i in ids}, {"resolved": True, "source": "read_fields.py"}


def stage_of(crop, g):
    """(stage, reason_or_None). A state the crop file flags as BOTH withered and
    harvest-ready (oilseed radish's second state) is `unknown`: which the game treats it
    as is not readable, and either answer would be a guess."""
    if g in crop["withered"] and g in crop["ready"]:
        return "unknown", ("the crop file flags this state both isWithered and "
                           "isHarvestReady, and which one the game treats it as is not readable")
    if g in crop["withered"]:
        return "dead", None
    if g in crop["cut"]:
        return "harvested", None
    if g in crop["ready"]:
        return "ready", None
    return "growing", None


def has_exit(crop, g):
    """True when some period's rows move a crop out of state g."""
    return any(src == g and dst != g for n in PERIODS
               for src, dst in crop["periods"][n]["rows"])


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        emit({"usage": USAGE})
        return
    savegame_dir, farm_id, config, install_arg, mods_arg, owned_spec = parse_args(sys.argv)

    install_dir, mods_dir, path_err = load_paths(config, install_arg, mods_arg)
    if install_dir is None and mods_dir is None and (install_arg or mods_arg):
        install_dir, mods_dir = install_arg, mods_arg
        path_err = None
    if install_dir is None:
        fail(path_err or "no install directory: pass --install-dir or --config", calibration_needed=True)

    map_mod, map_id, err = read_map_id(savegame_dir)
    if err:
        fail(err)
    resolver = PackageResolver(install_dir, mods_dir, map_mod)
    zip_err = resolver.open_map_zip()
    if zip_err:
        fail(f"{zip_err}. The map is a mod ({map_id}) and the base game's crop files are not "
             f"authoritative for it; refusing to project from them.", map_id=map_id)

    crops, unresolved, crops_source, cerr = load_crops(resolver, install_dir, map_id)
    if cerr:
        fail(f"could not read the crop list: {cerr}", crops_source=crops_source)
    if not crops:
        fail("no crop could be read, so no planting window or date can be projected.",
             unresolved=unresolved)

    global LIKELY_READING
    LIKELY_READING = reading_evidence(crops)["likely_reading"]
    day, dpp = read_calendar(savegame_dir)
    cur_idx = ((day - 1) // dpp) % 12
    cur_start = day - ((day - 1) % dpp)

    career, _g = load_xml(os.path.join(savegame_dir, "careerSavegame.xml"))
    gm = career.find(".//growthMode") if career is not None else None
    growth_mode = (gm.text or "").strip() if gm is not None else None

    mode_name = GROWTH_MODE_NAMES.get(growth_mode)
    seasonal_ok = growth_mode == SEASONAL_MODE
    if seasonal_ok:
        mode_reason = None
    elif growth_mode is None:
        mode_reason = ("careerSavegame.xml carries no <growthMode>, so it is not known "
                       "whether this save grows crops by the seasonal table")
    else:
        mode_reason = ("this save's growthMode is %s%s, not SEASONAL: seasonal growth is off, so "
                       "the game does not grow its crops by the seasonal period table. Players "
                       "report that crops can then be planted at any time and that how fast "
                       "they grow per day is a setting the player chooses in the game; neither "
                       "is read from data here, and the save files this skill reads do not "
                       "record that growth speed. No plant window and no ready or dead date is "
                       "given as fact; ask the player, or read the game's own field info, for timing"
                       % (growth_mode, " (%s)" % mode_name if mode_name else
                          ", a value the game's log has not been seen to name"))

    crop_rows = []
    for name in sorted(crops):
        c = crops[name]
        row = {"crop": c["name"], "source_file": c["source_file"],
               "resolved_from": c["resolved_from"], "state_names": c["state_names"]}
        if not seasonal_ok:
            row["status"] = "unknown"
            row["reason"] = mode_reason
        elif c["periods"] is None:
            row["status"] = "unknown"
            row["reason"] = c["seasonal_error"]
        else:
            row["status"] = "ok"
            row["plant_windows"] = plant_windows(c, day, cur_idx, cur_start, dpp)
            if not row["plant_windows"]:
                row["status"] = "unknown"
                row["reason"] = "no period of this crop's seasonal block allows planting"
        crop_rows.append(row)

    fields_root, generic = load_xml(os.path.join(savegame_dir, "fields.xml"))
    if fields_root is None:
        fail(f"could not read fields.xml: {generic.get('error')}")
    owned, ownership = owned_ids(savegame_dir, farm_id, config, mods_dir, owned_spec)

    field_rows = []
    for fld in fields_root.iter("field"):
        fid = fld.attrib.get("id")
        if owned is not None and fid not in owned:
            continue
        fruit = (fld.attrib.get("fruitType") or "").upper()
        try:
            g = int(fld.attrib.get("growthState", "0"))
        except ValueError:
            g = None
        row = {"field_id": fid, "owned": None if owned is None else True,
               "current_crop": fruit or None, "growth_state": g}
        if not fruit or fruit == "UNKNOWN" or g == 0:
            row.update(current_crop=None, stage="bare",
                       note="no crop standing: nothing to project; plant windows are per crop")
        elif g is None or g < 0:
            row.update(stage="unknown", reason="growthState is not a whole number of 0 or more")
        elif fruit not in crops:
            row.update(stage="unknown", reason=f"{fruit} has no readable crop file, so its states "
                                               f"and growth steps are unknown")
        else:
            c = crops[fruit]
            row.update(source_file=c["source_file"], resolved_from=c["resolved_from"])
            if g > len(c["state_names"]):
                row.update(stage="unknown", reason=f"growthState {g} is beyond the crop's "
                                                   f"{len(c['state_names'])} declared states")
            else:
                stage, stage_reason = stage_of(c, g)
                row.update(stage=stage, state_name=c["state_names"][g - 1])
                if stage_reason:
                    row["reason"] = stage_reason
                if not seasonal_ok:
                    row["reason"] = mode_reason
                    row["ready_to_harvest"] = {"status": "unknown", "from_day": None,
                                               "by_day": None, "likely_day": None,
                                               "reason": mode_reason}
                    row["dies"] = dict(row["ready_to_harvest"])
                elif c["periods"] is None:
                    row["reason"] = c["seasonal_error"]
                elif stage == "unknown":
                    pass
                elif stage in ("harvested", "dead") and not has_exit(c, g):
                    row["note"] = ("already %s and no growth row leaves this state: no further "
                                   "dates" % stage)
                else:
                    row.update(project_state(c, g, cur_idx, cur_start, dpp))
        field_rows.append(row)

    emit({
        "status": ("ok" if seasonal_ok and not unresolved and owned is not None
                   else "partial"),
        "farm_id": farm_id,
        "map_id": map_id,
        "crops_source": crops_source,
        "calendar": {
            "current_day": day,
            "days_per_period": dpp,
            "current_period": PERIODS[cur_idx],
            "current_period_first_day": cur_start,
            "formula": "((currentDay - 1) // daysPerPeriod) % 12",
            "day_counter": "environment.xml currentDay",
        },
        "growth_mode": {
            "value": growth_mode,
            "name": mode_name,
            "seasonal_table_applies": seasonal_ok,
            "reason": mode_reason,
            "note": ("careerSavegame.xml growthMode, named as the game's own log names it. "
                     "Only SEASONAL (1) is shown to follow the crops' <seasonal> table, so "
                     "only then are dates projected. Check one predicted window against the "
                     "game's own field info."),
        },
        "timing_model": {
            "readings": READINGS,
            "evidence": reading_evidence(crops),
            "window": ("every date is a window: from_day is the earlier reading, by_day the "
                       "later. alive_through_day is the last day the crop is certainly alive."),
            "assumptions": [
                "one update row per tick: no cascade inside a tick; a row from a state the "
                "field is not in does nothing",
                f"a crop is sown at state {SOWN_STATE}",
                "nothing outside the growth block (disaster, weather, harvest) intervenes",
                f"dates not reached within {HORIZON_TICKS} periods are unknown",
            ],
        },
        "ownership": ownership,
        "fields": field_rows,
        "crops": crop_rows,
        "unresolved_crops": unresolved,
    })


if __name__ == "__main__":
    main()
