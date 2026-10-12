"""
read_building_capacity.py -- how much each OWNED building can hold, and how full it is.

Usage: python3 read_building_capacity.py <savegame_dir> [--farm-id N]
                                         [--config PATH] [--install-dir DIR]
                                         [--mods-dir DIR]

WHY THIS SCRIPT EXISTS (FM-1001 item 4). In the owner's live test the manager
said twice that it could not tell whether anything was at capacity: "the save
records what a store holds, not what it can hold". True of the save; the other
half is in each building's own definition file, and nothing had joined the two.
The only capacity reader, `read_production_defs.py` `storage_capacities`,

  * reads only per-fill-type `<capacity>` rows under `<productionPoint>` -- never
    a storage's TOTAL `#capacity`, so a silo or a husbandry store (which declare
    only that) was invisible; and
  * is keyed [source_path, fill_type] with no building id, so the
    PRODUCTIONS tab can only reach a building through its recipe's source path,
    and refuses ("ambiguous") whenever two definitions that share a recipe
    disagree.

THE JOIN HERE IS BY THE BUILDING'S OWN FILE. The save records each placeable's
`filename`; `xml_utils.resolve_game_xml` opens exactly that file (an exact
full-path match inside the right mod zip, or under the install -- never a
basename search, F-019). So two buildings that share a recipe but have
different tanks each get their own figure, and a building whose file cannot be
opened is named with the reason and carries NO number.

WHAT A CAPACITY IS (engine source, `dataS/scripts/objects/Storage.lua`):
  * `<storage capacity=>` is the TOTAL, default 100000 when absent
    (Storage.lua:78). `<capacity fillType= capacity=>` rows are per-fill-type
    ceilings (Storage.lua:105-111).
  * `Storage:getCapacity(ft)` = the per-fill-type row, else the total
    (Storage.lua:411-413).
  * With `supportsMultipleFillTypes` (default true) a fill type WITHOUT its own
    row shares the total with every fill in the storage: free space is the total
    minus the sum of ALL fill levels (Storage.lua:471-486). A fill type WITH its
    own row has its own ceiling. Without multiple-fill-types support, one fill type at a
    time, ceiling = own row else total (Storage.lua:489-501).
This script reports each fill type's ceiling AND which of those it is
(`ceiling_basis`), and for shared fills the whole pool, so a percent is never
computed against the wrong denominator.

HOW THE SAVE MATCHES THE DEFINITION. A save `<storage>` sits under a container
(`productionPoint`, `silo`, `husbandry`, `siloExtension`, `constructible`,
`factory`). The definition's `<storage>` elements are grouped by the same
container (a silo's sit one level down, in `<storages>`). A silo save storage
carries `index` (1-based) into that list. With one candidate there is no
ambiguity; with several and no index the building is reported unresolved.

An empty storage is a storage with no `<node>`: the game omits nodes it holds at
zero (TD-139, measured), so a declared fill type with no node reads 0 and says so.

Output (stdout, one JSON document):
  {"status": "ok"|"partial", "farm_id", "buildings": [...], "summary": {...}}
Each building row: placeable_unique_id, filename, container, status
("resolved" | "unresolved"), and for resolved: capacity_total_litres (+
capacity_total_defaulted), supports_multiple_fill_types, entries[] (fill_type,
level_litres, ceiling_litres, ceiling_basis, percent_full -- only where the percent IS this
fill's own: a per-fill-type row, or a single-fill storage; a fill that shares the total carries
`percent_of_shared_pool` instead), is_empty, shared_pool when any
fill shares the total. An unresolved row has `reason` and no figure at all.

Could-not-run -- bad args or an unreadable placeables.xml -- emits {"error": ...} and
exits 1. Two answers about the SAVE are documents, exit 0, never errors: a farm with no
storage at all (`summary.confirmed_empty: true`, no buildings), and a farm none of whose
storages could be joined (every building listed `unresolved` with its reason, `status:
"partial"` and a top-level `reason`; typical of pre-placed buildings).

READ-ONLY: reads the savegame, the install and mod zips; writes nothing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, resolve_game_xml
from read_store_prices import load_paths

USAGE = ("read_building_capacity.py <savegame_dir> [--farm-id N] [--config PATH] "
         "[--install-dir DIR] [--mods-dir DIR]")

# Storage.lua:78 -- `xmlFile:getValue(key .. "#capacity", 100000)`.
ENGINE_DEFAULT_TOTAL = 100000.0

# OUR thresholds for the summary lists, stated in the output so nobody reads
# them as the game's. A figure at or above FULL_PCT is "full"; at or above
# NEAR_FULL_PCT is "near full".
FULL_PCT = 99.5
NEAR_FULL_PCT = 90.0

# Containers whose <storage> this script reads. A <storage> under any other
# parent is reported as unsupported, never skipped in silence.
CONTAINERS = ("productionPoint", "silo", "husbandry", "siloExtension",
              "constructible", "factory")


def fail(message, **extra):
    out = {"error": message}
    out.update(extra)
    emit(out)
    sys.exit(1)


def parse_args(argv):
    """(savegame_dir, farm_id, config, install_dir, mods_dir). Unknown flags and
    missing values are an error, never ignored."""
    args = argv[1:]
    savegame_dir = None
    farm_id, config, install_dir, mods_dir = 1, None, None, None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--farm-id", "--config", "--install-dir", "--mods-dir"):
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
            else:
                mods_dir = val
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
    return savegame_dir, farm_id, config, install_dir, mods_dir


def to_float(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def container_of(element, parent_map):
    """The container a <storage> belongs to: its parent's tag, or -- for a silo's
    <storages><storage> -- the grandparent's."""
    parent = parent_map.get(element)
    if parent is not None and parent.tag == "storages":
        parent = parent_map.get(parent)
    return parent.tag if parent is not None else None


def definition_storages(def_root):
    """{container: [<storage> element, ...]} in document order."""
    parent_map = {c: p for p in def_root.iter() for c in p}
    grouped = {}
    for storage in def_root.iter("storage"):
        grouped.setdefault(container_of(storage, parent_map), []).append(storage)
    return grouped


def describe_storage(def_storage):
    """The numbers one definition <storage> declares. Returns (spec, error)."""
    raw_total = def_storage.attrib.get("capacity")
    if raw_total is None:
        total, defaulted = ENGINE_DEFAULT_TOTAL, True
    else:
        total, defaulted = to_float(raw_total), False
        if total is None:
            return None, f"storage capacity={raw_total!r} is not a number"
    per_type = {}
    for row in def_storage.findall("capacity"):
        ft = row.attrib.get("fillType")
        if not ft:
            return None, "a <capacity> row has no fillType"
        raw = row.attrib.get("capacity")
        # Storage.lua:106 -- a row with no capacity attribute is 100000.
        cap = ENGINE_DEFAULT_TOTAL if raw is None else to_float(raw)
        if cap is None:
            return None, f"<capacity fillType={ft!r}> capacity={raw!r} is not a number"
        per_type[ft.upper()] = cap
    multi = def_storage.attrib.get("supportsMultipleFillTypes", "true").strip().lower()
    return {
        "total": total,
        "total_defaulted": defaulted,
        "per_type": per_type,
        "supports_multiple": multi != "false",
        "is_extension": def_storage.attrib.get("isExtension"),
    }, None


def save_fill_levels(save_storage):
    """({FILLTYPE: litres}, error). A <node> without a readable level is an error
    for that building, never a quiet 0."""
    levels = {}
    for node in save_storage.findall("node"):
        ft = node.attrib.get("fillType")
        if not ft:
            return None, "a <node> in the save has no fillType"
        raw = node.attrib.get("fillLevel")
        # Storage.registerSavegameXMLPaths: fillLevel defaults to 0.
        level = 0.0 if raw is None else to_float(raw)
        if level is None:
            return None, f"<node fillType={ft!r}> fillLevel={raw!r} is not a number"
        levels[ft.upper()] = levels.get(ft.upper(), 0.0) + level
    return levels, None


def build_entries(spec, levels):
    """Per fill type: level, ceiling, which kind of ceiling, percent full."""
    fill_types = sorted(set(spec["per_type"]) | set(levels))
    pool_used = sum(levels.values())
    entries, shares_total = [], False
    for ft in fill_types:
        level = levels.get(ft, 0.0)
        own = spec["per_type"].get(ft)
        entry = {
            "fill_type": ft,
            "level_litres": round(level, 3),
            "level_basis": ("a <node> in the save" if ft in levels else
                            "no <node> in the save: the game omits a storage it "
                            "holds at zero, so this fill type is empty"),
        }
        if own is not None:
            entry.update(ceiling_litres=own, ceiling_basis="per_fill_type")
            pct = (level / own * 100.0) if own else None
            entry["percent_full"] = None if pct is None else round(pct, 2)
        elif spec["supports_multiple"]:
            # THE PERCENT HERE IS THE POOL'S, not this fill's own share: it is named so, and
            # no `percent_full` key is given, so it cannot be quoted as this fill's figure.
            shares_total = True
            entry.update(ceiling_litres=spec["total"], ceiling_basis="shared_total")
            pct = (pool_used / spec["total"] * 100.0) if spec["total"] else None
            entry["percent_of_shared_pool"] = None if pct is None else round(pct, 2)
            entry["percent_note"] = ("the shared pool's percent, not this fill type's own "
                                     "share; see shared_pool")
        else:
            # supportsMultipleFillTypes="false": one fill type at a time, so the total IS
            # this fill type's ceiling (Storage.lua:489-501).
            entry.update(ceiling_litres=spec["total"], ceiling_basis="total_single_fill")
            pct = (level / spec["total"] * 100.0) if spec["total"] else None
            entry["percent_full"] = None if pct is None else round(pct, 2)
        entries.append(entry)
    pool = None
    if shares_total:
        pct = (pool_used / spec["total"] * 100.0) if spec["total"] else None
        pool = {
            "used_litres": round(pool_used, 3),
            "ceiling_litres": spec["total"],
            "percent_full": None if pct is None else round(pct, 2),
            "note": ("fill types with ceiling_basis \"shared_total\" share this one pool; "
                     "the free space is the total minus EVERY fill level in the "
                     "storage (Storage.lua getFreeCapacity)."),
        }
    return entries, pool


def ceiling_for_fill_type(filename, container, fill_type, install_dir, mods_dir, cache):
    """One building's ceiling for one fill type, joined by the building's OWN file.

    Returns (litres_or_None, reason_or_None, kind). kind is "resolved", "no_own_row" (the
    building's own file was read and declares no row for this fill type: a settled answer
    about THIS building, nothing to fall back to) or "unjoined" (the file could not be
    found, opened or told apart: the building was never reached). Used by emit_productions_xml.py (item 9)
    so the PRODUCTIONS tab no longer reaches a building through its recipe's source
    path. A figure comes back ONLY for a fill type with its own <capacity> row: a fill
    type without one shares the storage's total with every other fill in it
    (Storage.lua getFreeCapacity), so the total alone is not "this fill type's
    capacity" and is refused with that reason rather than shown as one. `cache` is a
    dict the caller keeps across calls (one file read per distinct filename)."""
    if not filename:
        return None, ("the placeable has no filename (a pre-placed map object), so there "
                      "is no definition file to join to"), "unjoined"
    if filename not in cache:
        def_root, label, kind, err = resolve_game_xml(filename, install_dir, mods_dir)
        cache[filename] = ((definition_storages(def_root), label, None)
                           if def_root is not None else (None, None, f"({kind}) {err}"))
    groups, label, err = cache[filename]
    if groups is None:
        return None, f"the building's definition file was not opened {err}", "unjoined"
    candidates = groups.get(container) or []
    if not candidates:
        return None, f"{label} declares no <storage> under <{container}>", "unjoined"
    if len(candidates) > 1:
        return None, (f"{label} declares {len(candidates)} storages under <{container}> and "
                      f"the save does not say which one this is"), "unjoined"
    spec, spec_err = describe_storage(candidates[0])
    if spec_err:
        return None, f"{label}: {spec_err}", "unjoined"
    own = spec["per_type"].get(str(fill_type).upper())
    if own is not None:
        return own, None, "resolved"
    if not spec["supports_multiple"]:
        # supportsMultipleFillTypes="false": one fill type at a time, so the total is this
        # fill type's own ceiling (Storage.lua:489-501).
        return spec["total"], None, "resolved"
    return None, (f"{label} declares no capacity row for {fill_type}; it shares the storage's "
                  f"total of {spec['total']:g} L with every other fill type in it, so the "
                  f"total is not this fill type's own capacity"), "no_own_row"


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        emit({"usage": USAGE})
        return
    savegame_dir, farm_id, config, install_arg, mods_arg = parse_args(sys.argv)

    install_dir, mods_dir, _paths_err = load_paths(config, install_arg, mods_arg)
    if install_dir is None and mods_dir is None and (install_arg or mods_arg):
        install_dir, mods_dir = install_arg, mods_arg
    # A path problem is not fatal here: resolve_game_xml names it per building.

    placeables_path = os.path.join(savegame_dir, "placeables.xml")
    root, generic = load_xml(placeables_path)
    if root is None:
        fail(f"could not read placeables.xml: {generic.get('error')}", file=placeables_path)

    cache = {}

    def definition_for(filename):
        if filename not in cache:
            def_root, label, kind, err = resolve_game_xml(filename, install_dir, mods_dir)
            cache[filename] = (
                (definition_storages(def_root), label, kind, None)
                if def_root is not None else (None, None, kind, err))
        return cache[filename]

    save_parent = {c: p for p in root.iter() for c in p}
    buildings = []
    owned = 0
    for placeable in root.iter("placeable"):
        try:
            if int(placeable.attrib.get("farmId", "")) != farm_id:
                continue
        except ValueError:
            continue
        owned += 1
        uid = placeable.attrib.get("uniqueId")
        filename = placeable.attrib.get("filename") or ""
        for save_storage in placeable.iter("storage"):
            parent = save_parent.get(save_storage)
            container = parent.tag if parent is not None else None
            row = {"placeable_unique_id": uid, "filename": filename,
                   "container": container}
            if container not in CONTAINERS:
                row.update(status="unresolved", reason=(
                    f"a <storage> under <{container}> is not a container this script "
                    f"reads ({', '.join(CONTAINERS)}); no capacity is claimed."))
                buildings.append(row)
                continue
            if not filename:
                row.update(status="unresolved", reason=(
                    "the placeable has no filename (a pre-placed map object), so there "
                    "is no definition file to join to."))
                buildings.append(row)
                continue
            groups, label, kind, err = definition_for(filename)
            if groups is None:
                row.update(status="unresolved", reason=(
                    f"definition file not opened ({kind}): {err}"))
                buildings.append(row)
                continue
            candidates = groups.get(container) or []
            raw_index = save_storage.attrib.get("index")
            if not candidates:
                row.update(status="unresolved", definition=label, reason=(
                    f"the definition declares no <storage> under <{container}>."))
                buildings.append(row)
                continue
            if raw_index is not None:
                try:
                    pick = candidates[int(raw_index) - 1]
                    if int(raw_index) < 1:
                        raise IndexError
                except (ValueError, IndexError):
                    row.update(status="unresolved", definition=label, reason=(
                        f"the save's storage index={raw_index!r} does not point at "
                        f"one of the {len(candidates)} storage(s) the definition "
                        f"declares."))
                    buildings.append(row)
                    continue
            elif len(candidates) == 1:
                pick = candidates[0]
            else:
                row.update(status="unresolved", definition=label, reason=(
                    f"the definition declares {len(candidates)} storages under "
                    f"<{container}> and the save's storage carries no index, so "
                    f"nothing says which one this is."))
                buildings.append(row)
                continue
            spec, spec_err = describe_storage(pick)
            levels, level_err = save_fill_levels(save_storage)
            if spec_err or level_err:
                row.update(status="unresolved", definition=label,
                           reason=spec_err or level_err)
                buildings.append(row)
                continue
            entries, pool = build_entries(spec, levels)
            row.update(
                status="resolved", definition=label,
                is_extension=spec["is_extension"],
                capacity_total_litres=spec["total"],
                capacity_total_defaulted=spec["total_defaulted"],
                supports_multiple_fill_types=spec["supports_multiple"],
                entries=entries,
                is_empty=(sum(levels.values()) == 0))
            if spec["total_defaulted"]:
                row["capacity_total_note"] = (
                    "the definition declares no total; the engine default 100000 "
                    "applies (Storage.lua:78).")
            if pool is not None:
                row["shared_pool"] = pool
            buildings.append(row)

    resolved = [b for b in buildings if b["status"] == "resolved"]
    unresolved = [b for b in buildings if b["status"] != "resolved"]
    if not buildings:
        # A confirmed-empty answer about THIS save, not an error and not a capacity of zero.
        emit({
            "status": "ok", "farm_id": farm_id, "buildings": [],
            "summary": {
                "storages_total": 0, "resolved": 0, "unresolved": 0, "full": [],
                "near_full": [], "confirmed_empty": True,
                "note": (f"farm {farm_id} owns {owned} placeable(s) and none carries a "
                         f"<storage> in the save: it stores nothing in a building. That is a "
                         f"measurement of this save, not a capacity of zero."),
            },
        })
        return

    def pcts(b):
        vals = [e["percent_full"] for e in b["entries"]
                if e.get("percent_full") is not None]
        if b.get("shared_pool") and b["shared_pool"]["percent_full"] is not None:
            vals.append(b["shared_pool"]["percent_full"])
        return vals

    full, near = [], []
    for b in resolved:
        top = max(pcts(b), default=None)
        if top is None:
            continue
        tag = {"placeable_unique_id": b["placeable_unique_id"],
               "filename": b["filename"], "container": b["container"],
               "highest_percent_full": top}
        if top >= FULL_PCT:
            full.append(tag)
        elif top >= NEAR_FULL_PCT:
            near.append(tag)

    emit({
        "status": "ok" if not unresolved else "partial",
        "farm_id": farm_id,
        "buildings": buildings,
        **({"reason": ("not one storage could be joined to its definition file, so no capacity "
                       "is known for any of them. Each is listed with its reason. This is NOT a "
                       "report that nothing has a ceiling.")} if not resolved else {}),
        "summary": {
            "storages_total": len(buildings),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "full": full,
            "near_full": near,
            "thresholds_note": (
                f"full = {FULL_PCT}% or more, near full = {NEAR_FULL_PCT}% or more: "
                f"this script's own cut-offs, not the game's."),
            "unresolved_note": (
                "every unresolved building is listed in `buildings` with its reason "
                "and NO figure; name each one to the player, never fold it into 'not full'."
                if unresolved else None),
        },
    })


if __name__ == "__main__":
    main()
