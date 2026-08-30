"""
Read farm cash/loan and field ownership for one farm in an FS25 savegame.

Usage: python3 read_economy.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

Reads TWO files, NOT economy.xml:
    farms.xml     -> <farm farmId="1" name="My farm" color="1"
                            loan="0.000000" money="88575568.000000"> ...
                      Cash and loan live on the <farm> element's attributes.
    farmland.xml  -> <farmland id="N" farmId="M"/>
                      One entry per map parcel. farmId="0" means unowned/NPC
                      land; farmId matching the target farm means owned by
                      that farm. Ownership is derived by filtering on farmId,
                      not by any per-field "owned" flag.

economy.xml is NOT read here: in this save (and apparently FS25 generally)
it contains only fillType sale-price history, e.g.
    <fillType fillType="WHEAT"><history><period period="EARLY_SPRING">337</period>...
It has no cash, loan, or ownership data. A prior version of this script read
economy.xml and hunted for a <fieldOwnership><field number= ownedByPlayer=>
structure; that structure does not exist in this save and the docstring's
claim that it was "community-verified" was false. That bug produced a
silent, wrong "you own 0 fields" result. This version fails loudly instead
of guessing.

Output contract:
    - Never returns [] / {} / a guess for missing data. If farms.xml or
      farmland.xml is missing, or the expected attributes aren't present,
      or the requested --farm-id doesn't exist, this emits {"error": "..."}
      explaining exactly what's missing.
    - calibration_needed is true ONLY when the expected tags/attributes could
      not be confidently located (i.e. the schema looks different than
      expected) -- never merely because a count came out to zero. A farm
      that genuinely owns 0 parcels, or has 0 cash, is a valid, non-
      calibration result.
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
                return None, "usage: read_economy.py <savegame_dir> [--farm-id N] -- --farm-id given with no value"
            try:
                farm_id = int(args[i + 1])
            except ValueError:
                return None, f"--farm-id must be an integer, got {args[i + 1]!r}"
            i += 2
        else:
            i += 1
    return farm_id, None


def main():
    savegame_dir = arg_or_exit("read_economy.py <savegame_dir> [--farm-id N]")
    farm_id, arg_err = parse_farm_id_arg(sys.argv)
    if arg_err:
        emit({"error": arg_err, "calibration_needed": False})
        return

    farms_path = os.path.join(savegame_dir, "farms.xml")
    farmland_path = os.path.join(savegame_dir, "farmland.xml")

    farms_root, farms_generic = load_xml(farms_path)
    if farms_root is None:
        emit({
            "error": f"could not read farms.xml: {farms_generic.get('error')}",
            "calibration_needed": True,
        })
        return

    farmland_root, farmland_generic = load_xml(farmland_path)
    if farmland_root is None:
        emit({
            "error": f"could not read farmland.xml: {farmland_generic.get('error')}",
            "calibration_needed": True,
        })
        return

    # --- Parse all <farm> elements ---
    all_farms = []
    for farm_elem in farms_root.iter("farm"):
        attrs = farm_elem.attrib
        if "farmId" not in attrs:
            continue
        try:
            fid = int(attrs["farmId"])
        except ValueError:
            continue
        money_raw = attrs.get("money")
        loan_raw = attrs.get("loan")
        all_farms.append({
            "farm_id": fid,
            "name": attrs.get("name"),
            "color": attrs.get("color"),
            "cash": float(money_raw) if money_raw is not None else None,
            "loan": float(loan_raw) if loan_raw is not None else None,
            "_has_money_attr": money_raw is not None,
            "_has_loan_attr": loan_raw is not None,
        })

    if not all_farms:
        emit({
            "error": (
                "farms.xml parsed but contained no <farm farmId=...> elements -- "
                "schema may have changed."
            ),
            "calibration_needed": True,
            "generic_dump": farms_generic,
        })
        return

    target_farm = next((f for f in all_farms if f["farm_id"] == farm_id), None)
    if target_farm is None:
        emit({
            "error": (
                f"farm_id {farm_id} not found in farms.xml. "
                f"Available farm_ids: {sorted(f['farm_id'] for f in all_farms)}"
            ),
            "calibration_needed": False,
        })
        return

    if not target_farm["_has_money_attr"] or not target_farm["_has_loan_attr"]:
        emit({
            "error": (
                f"farm_id {farm_id} found in farms.xml but is missing 'money' and/or "
                f"'loan' attributes -- schema may have changed."
            ),
            "calibration_needed": True,
            "farm_element_attrs": dict(farms_root.find(f".//farm[@farmId='{farm_id}']").attrib)
            if farms_root.find(f".//farm[@farmId='{farm_id}']") is not None else None,
        })
        return

    # --- Parse all <farmland> elements ---
    farmland_entries = []
    for fl_elem in farmland_root.iter("farmland"):
        attrs = fl_elem.attrib
        if "id" not in attrs or "farmId" not in attrs:
            continue
        try:
            fl_id = int(attrs["id"])
            fl_farm_id = int(attrs["farmId"])
        except ValueError:
            continue
        farmland_entries.append((fl_id, fl_farm_id))

    if not farmland_entries:
        emit({
            "error": (
                "farmland.xml parsed but contained no <farmland id=... farmId=...> "
                "elements -- schema may have changed."
            ),
            "calibration_needed": True,
            "generic_dump": farmland_generic,
        })
        return

    total_parcels = len(farmland_entries)
    owned_parcel_ids = sorted(fl_id for fl_id, fl_farm_id in farmland_entries if fl_farm_id == farm_id)
    unowned_parcel_ids = [fl_id for fl_id, fl_farm_id in farmland_entries if fl_farm_id == 0]

    other_farms = [
        {
            "farm_id": f["farm_id"],
            "name": f["name"],
            "cash": f["cash"],
            "loan": f["loan"],
        }
        for f in all_farms
        if f["farm_id"] != farm_id
    ]

    emit({
        "sources": {"farms": farms_path, "farmland": farmland_path},
        "farm_id": farm_id,
        "farm_name": target_farm["name"],
        "cash": target_farm["cash"],
        "loan": target_farm["loan"],
        "land": {
            "owned_parcel_ids": owned_parcel_ids,
            "owned_count": len(owned_parcel_ids),
            "unowned_count": len(unowned_parcel_ids),
            "total_parcels": total_parcels,
        },
        "other_farms": other_farms,
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
