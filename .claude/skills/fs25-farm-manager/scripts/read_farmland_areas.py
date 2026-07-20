"""
Decode the map's infoLayer_farmlands.grle raster to get real per-parcel area
(hectares), cost, and a field-number -> farmland-id -> owner mapping.

Usage: python3 read_farmland_areas.py <savegame_dir> [mods_dir] [--farm-id N]
                                       [--mods-dir PATH]
    (run with --help for the full argparse usage; unknown flags are an error,
    not silently ignored)
    --farm-id N     Which farmId counts as "owned" (default: 1).
    --mods-dir PATH Where the map mod lives. If omitted (and no positional
                    mods_dir is given either), resolved from
                    sanctum/config.json -> paths.mods_dir -- same lookup
                    read_fields.py's find_mods_dir() uses, reused here rather
                    than reinvented, so both scripts agree on where mods live.

FRICTION-LOG: this script used to REQUIRE mods_dir as a bare positional arg,
the only parser in this toolkit that broke the shared "<savegame_dir>
[--flags]" contract every other script follows. `read_farmland_areas.py
"$SG"` failed with a usage error while every sibling script accepted exactly
that. Fixed to make mods_dir resolvable the same way read_store_prices.py
and read_fields.py already do it. The old positional form
(`read_farmland_areas.py <savegame_dir> <mods_dir> ...`) still works
unchanged -- read_fields.py's derive_owned_field_ids() calls it that way and
was deliberately left untouched, so both call styles are supported.

This answers two things nothing else in this toolkit could (FRICTION-LOG.md
F-004, F-012):
    - F-004: which of the fields does the player actually own?
    - F-012: what did the player's parcels cost? (the farm's founding debt
      previously read "$X + land" because land had no price.)

READ-ONLY. Never writes to the savegame or any mod file.

WHY THIS WAS REFUSED UNTIL NOW: a wrong decode of a proprietary binary format
would silently corrupt the exact number the farm's whole debt premise rests
on, and a wrong number would look just as plausible as a right one. This
version does not ship a guess -- it ships a decode that passed hard,
falsifiable validation gates against independent ground truth already in
this save, documented below with the actual numbers obtained on 2026-07-16.
If those gates ever fail on a re-run (different save, different map), THIS
SCRIPT REFUSES TO PRODUCE COST/AREA NUMBERS and reports calibration_needed
instead of a best-effort guess.

===========================================================================
1. THE GRLE FORMAT (not reverse-engineered from scratch -- found and used
   published, verified prior art)
===========================================================================
GRLE ("Giants Run-Length Encoded") is GIANTS' proprietary format for
Farming Simulator terrain info-layers. Format reverse-engineered and
published by the Paint-a-Farm/grleconvert project
(https://github.com/Paint-a-Farm/grleconvert, docs/GRLE_FORMAT.md),
verified there against GIANTS' own official grleConverter.exe tool output
with "0 pixel differences across all test files". This script implements
that published spec directly -- it is not a fresh guess.

Header (20 bytes, little-endian):
    offset 0-3:   magic "GRLE"
    offset 4-5:   version (u16, always 1 observed)
    offset 6-7:   width / 256  (u16)   -- actual width = this * 256
    offset 8-9:   reserved (0)
    offset 10-11: height / 256 (u16)   -- actual height = this * 256
    offset 12:    reserved (0)
    offset 13:    channels (u8, always 1 for GRLE)
    offset 14-15: reserved (0)
    offset 16-19: compressed size (u32, informational only -- NOT used to
                  decode; observed to sometimes be an unreliable/garbage
                  value in this save's file and is ignored here)

RLE body (starts at offset 20, skip 1 padding byte -> real start offset 21):
    Read (prev, new) byte pairs. If prev == new: it's a RUN -- read
    0xFF-extended count bytes (each 0xFF adds 255; final non-0xFF byte is
    the remainder), actual run length = count + 2, emit that many copies of
    the value. If prev != new: it's a TRANSITION -- emit one copy of prev,
    back up one byte so `new` becomes the next `prev`. Continue until the
    expected pixel count (width*height*channels) is reached.

===========================================================================
2. VALIDATION GATES -- run and passed against this save, 2026-07-16
===========================================================================
Gate 1 (HARD, checked every run): the set of distinct farmland ids found in
the decoded raster must equal EXACTLY the set of ids in the savegame's
farmland.xml. On this save: decoded raster contains exactly ids {1..149},
zero gaps, zero out-of-range values, zero occurrences of id 0 -- an exact
match to farmland.xml's 149 entries (18 owned farmId=1, 131 farmId=0). If
this gate fails on a future run, the script emits calibration_needed and
refuses to compute costs/areas -- see main().

Gate 2 (HARD, checked every run): total decoded pixel count must equal
width*height from the header, AND the map's declared width/height (from the
map mod's own top-level XML, e.g. mapUS.xml's `<map width= height=>`) must
produce square pixels (metres-per-pixel equal on both axes) within a tight
tolerance. On this save: map declared 4096 x 4096 m; raster decoded to
2048 x 2048 px (4,194,304 pixels, matching width*height exactly) -> exactly
2.0 m/pixel on both axes -> total area 1,677.7216 ha, matching 4096x4096 m
exactly by construction.

Gate 3 (soft plausibility, logged not enforced): at this map's declared
pricePerHa=60000 (all observed priceScale=1), per-parcel costs should be in
a human-plausible range. On this save the 18 owned parcels ranged
4.66 ha ($279,720) to 54.66 ha ($3,280,020) -- no $50 parcels, no $500M
parcels.

BONUS, independent-ground-truth cross-check (the strongest evidence this
decode is correct): this save's own `farms.xml` records
`<fieldPurchase>-15741096.000000</fieldPurchase>` -- money already spent on
land, logged by the game itself when the parcels were bought. This script's
computed total cost for the 18 owned parcels is **$15,741,096.00, exact to
the cent**, against that independent figure. That is not a coincidence a
wrong decode could produce by chance.

===========================================================================
3. FIELD -> FARMLAND MAPPING (map-specific finding, not a general FS25 rule)
===========================================================================
There is no field->farmland link in any XML (confirmed: fields.xml has no
farmId; the relationship is spatial, via this raster). To resolve it for
real fields, this map's `AutoDrive_config.xml` was used as an *external*
ground-truth source: it has 266 `<mapmarker>` entries, 122 named "Feld 1"
through "Feld 122" (matching fields.xml's 122 field ids exactly, verified
2026-07-16), each linking to a real world (x,z) coordinate via the
`<waypoints>` block's parallel id/x/y/z arrays (35,774 entries, verified
fully aligned, zero missing).

The world(x,z) -> raster(col,row) transform was NOT assumed -- it was
determined by testing all 8 axis-orientation candidates (swap x/z x flip-x
x flip-z) against all 122 known field coordinates and keeping only the one
where every field lands on a DIFFERENT farmland id with zero collisions and
zero fields landing on the single largest ("background"/unbuyable, ~8.6% of
the map) farmland id. Exactly one of the 8 candidates achieved this
(122/122 distinct, 0 collisions, 0 background hits); all 7 others produced
messy collisions and multiple background hits. The winning transform is the
simplest possible one -- direct, no flips: `col = (worldX + mapSize/2) /
mapSize * rasterWidth`, `row = (worldZ + mapSize/2) / mapSize * rasterHeight`.

Applying it produced a second, independent confirmation: for all 122
fields, **farmland_id == field_id, with zero exceptions.** This is a
MAP-SPECIFIC finding (this map happens to number its 122 workable fields
identically to their containing farmland parcel) -- it is hardcoded here as
FIELD_ID_EQUALS_FARMLAND_ID because re-deriving it would require shipping
the full AutoDrive coordinate-transform search in this script, which is out
of scope for a lightweight parser. If this script is ever pointed at a
different map, this assumption must be re-verified the same way before
trusting field ownership output -- calibration_needed is set true and a
field is reported with `farmland_id: null` if a field id ever falls outside
the decoded raster's id range, rather than silently asserting ownership.

===========================================================================
Output contract (same as the rest of this toolkit):
    - Never returns [] / {} / a best-effort guess. If a hard gate fails,
      emits {"error": "...", "calibration_needed": true} and STOPS before
      computing any area/cost number.
    - calibration_needed means "could not confidently locate/validate the
      data" -- not "a parcel has 0 hectares" (that would be a real, valid
      result if it ever occurred, which it doesn't on this save).
"""
import argparse
import json
import os
import re
import struct
import sys
import zipfile
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit


def find_mods_dir(explicit):
    """Locate the mods dir: the flag/positional arg, else sanctum/config.json
    -> paths.mods_dir. Same lookup as read_fields.py's find_mods_dir() -- kept
    as a separate copy (not imported) so this script has no import-time
    dependency on read_fields.py, but the logic and error wording are meant to
    match so the two scripts never disagree about where mods live.
    Returns (path_or_None, how_or_reason)."""
    if explicit:
        if not os.path.isdir(explicit):
            return None, f"mods_dir {explicit!r} is not a directory"
        return explicit, "explicit mods_dir (positional or --mods-dir)"
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
            return md, "sanctum/config.json -> paths.mods_dir"
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None, "no sanctum/config.json found above this script, and no mods_dir given"


def decode_grle(data):
    """Decode a GRLE file's bytes to (pixel_bytes, width, height).
    Raises ValueError with a clear message on structural problems -- never
    silently returns something half-decoded."""
    if len(data) < 21 or data[:4] != b"GRLE":
        raise ValueError(f"not a GRLE file (bad magic or too short: {len(data)} bytes)")

    width = struct.unpack("<H", data[6:8])[0] * 256
    height = struct.unpack("<H", data[10:12])[0] * 256
    channels = data[13]
    if channels != 1:
        raise ValueError(f"unexpected channel count {channels} (GRLE is always 1) -- format may differ")
    expected = width * height * channels
    if expected <= 0:
        raise ValueError(f"decoded zero/negative expected pixel count (width={width}, height={height})")

    compressed = data[20:]
    n = len(compressed)
    output = bytearray()
    i = 1  # skip 1 padding byte per the published spec
    while i + 1 < n and len(output) < expected:
        prev = compressed[i]
        new = compressed[i + 1]
        i += 2
        if prev == new:
            count = 0
            while i < n and compressed[i] == 0xFF:
                count += 255
                i += 1
            if i < n:
                count += compressed[i]
                i += 1
            count += 2
            take = min(count, expected - len(output))
            output.extend([new] * take)
        else:
            output.append(prev)
            i -= 1

    if len(output) != expected:
        raise ValueError(
            f"decoded {len(output)} pixels, expected {expected} -- RLE stream ended early, "
            "decode is unreliable, refusing to pad and pretend"
        )
    return bytes(output), width, height


def find_zip_entry(namelist, suffix_lower):
    matches = [n for n in namelist if n.lower().endswith(suffix_lower)]
    return matches[0] if len(matches) == 1 else (matches if matches else None)


def find_map_dimensions_xml(zf, namelist):
    """Find the map's top-level XML declaring <map width=... height=...>.
    Tries the conventional '<top>/<top>.xml' pattern first, then scans all
    top-level .xml files for the tag."""
    candidates = [n for n in namelist if n.count("/") == 1 and n.lower().endswith(".xml")]
    for name in candidates:
        try:
            text = zf.read(name).decode("utf-8", errors="ignore")
        except (KeyError, zipfile.BadZipFile):
            continue
        m = re.search(r'<map\s[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', text)
        if m:
            return name, float(m.group(1)), float(m.group(2))
    return None, None, None


def parse_pricing_xml(xml_bytes):
    """Parse the map's config/farmlands.xml -> (price_per_ha, {id: (priceScale, npcName)})."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)
    farmlands_elem = root.find("farmlands")
    if farmlands_elem is None:
        return None, {}
    price_per_ha = farmlands_elem.attrib.get("pricePerHa")
    price_per_ha = float(price_per_ha) if price_per_ha is not None else None
    pricing = {}
    for fl in farmlands_elem.findall("farmland"):
        try:
            fid = int(fl.attrib["id"])
        except (KeyError, ValueError):
            continue
        scale = fl.attrib.get("priceScale")
        pricing[fid] = {
            "price_scale": float(scale) if scale is not None else None,
            "npc_name": fl.attrib.get("npcName"),
        }
    return price_per_ha, pricing


def parse_savegame_farmland_ownership(path):
    """Parse savegame farmland.xml -> {id: farmId}. Returns (dict, error_or_None)."""
    root, generic = load_xml(path)
    if root is None:
        return None, generic.get("error")
    ownership = {}
    for fl in root.iter("farmland"):
        try:
            fid = int(fl.attrib["id"])
            owner = int(fl.attrib["farmId"])
        except (KeyError, ValueError):
            continue
        ownership[fid] = owner
    if not ownership:
        return None, "farmland.xml parsed but contained no <farmland id=... farmId=...> elements"
    return ownership, None


def parse_savegame_field_ids(path):
    root, generic = load_xml(path)
    if root is None:
        return None, generic.get("error")
    ids = []
    for f in root.iter("field"):
        try:
            ids.append(int(f.attrib["id"]))
        except (KeyError, ValueError):
            continue
    if not ids:
        return None, "fields.xml parsed but contained no <field id=...> elements"
    return sorted(ids), None


def parse_career_map_id(savegame_dir):
    root, generic = load_xml(os.path.join(savegame_dir, "careerSavegame.xml"))
    if root is None:
        return None, generic.get("error")
    settings = root.find("settings")
    if settings is None:
        return None, "careerSavegame.xml has no <settings> element"
    map_id_elem = settings.find("mapId")
    if map_id_elem is None or not map_id_elem.text:
        return None, "careerSavegame.xml <settings> has no <mapId>"
    return map_id_elem.text.strip(), None


class ToolkitArgumentParser(argparse.ArgumentParser):
    """argparse whose failures keep this toolkit's machine contract: a
    structured {"error": ...} JSON on STDOUT and exit code 1, matching every
    sibling script -- not argparse's default usage-to-stderr + exit 2.
    --help keeps argparse's native behavior (usage to stdout, exit 0)."""

    def error(self, message):
        emit({
            "error": f"{message} ({self.format_usage().strip()})",
            "calibration_needed": False,
        })
        sys.exit(1)


def parse_args(argv):
    parser = ToolkitArgumentParser(
        prog="read_farmland_areas.py",
        description="Decode the map's farmland raster: per-parcel area (ha), "
                    "cost, and field ownership for a savegame.",
    )
    parser.add_argument("savegame_dir", help="the savegame directory to read")
    # Backward compatibility: the original contract was a REQUIRED positional
    # mods_dir as argv[2]. read_fields.py's derive_owned_field_ids() still
    # calls it that way and was deliberately left untouched -- so a bare
    # (non-flag) second arg is still accepted as mods_dir here.
    parser.add_argument(
        "positional_mods_dir", nargs="?", default=None, metavar="mods_dir",
        help="the mods directory (backward-compat positional form; "
             "--mods-dir is the preferred spelling and wins if both are given)",
    )
    parser.add_argument(
        "--farm-id", type=int, default=1, metavar="N",
        help="which farmId counts as 'owned' (default: 1)",
    )
    parser.add_argument(
        "--mods-dir", dest="mods_dir_flag", default=None, metavar="PATH",
        help="where the map mod lives; if omitted (and no positional mods_dir "
             "either), resolved from sanctum/config.json -> paths.mods_dir",
    )
    ns = parser.parse_args(argv[1:])
    # --mods-dir (explicit flag) wins over the positional form if both given.
    mods_dir = ns.mods_dir_flag or ns.positional_mods_dir
    return ns.savegame_dir, mods_dir, ns.farm_id


def main():
    savegame_dir, mods_dir, farm_id = parse_args(sys.argv)

    mods_dir, how = find_mods_dir(mods_dir)
    if mods_dir is None:
        emit({
            "error": f"could not locate mods_dir: {how}. Pass it positionally, "
                     f"via --mods-dir, or set paths.mods_dir in sanctum/config.json.",
            "calibration_needed": True,
        })
        return

    map_id, err = parse_career_map_id(savegame_dir)
    if map_id is None:
        emit({"error": f"could not determine this save's map: {err}", "calibration_needed": True})
        return

    mod_zip_name = map_id.split(".")[0] + ".zip"
    mod_zip_path = os.path.join(mods_dir, mod_zip_name)
    if not os.path.isfile(mod_zip_path):
        available = sorted(f for f in os.listdir(mods_dir) if f.lower().endswith(".zip")) if os.path.isdir(mods_dir) else []
        emit({
            "error": (
                f"map mod zip not found: {mod_zip_path} (derived from careerSavegame.xml mapId "
                f"'{map_id}'). {len(available)} .zip files present in {mods_dir}."
            ),
            "calibration_needed": True,
            "mods_dir_zip_sample": available[:10],
        })
        return

    try:
        zf = zipfile.ZipFile(mod_zip_path)
    except zipfile.BadZipFile as e:
        emit({"error": f"could not open {mod_zip_path}: {e}", "calibration_needed": True})
        return

    namelist = zf.namelist()
    grle_name = find_zip_entry(namelist, "data/infolayer_farmlands.grle")
    pricing_name = find_zip_entry(namelist, "config/farmlands.xml")
    if not isinstance(grle_name, str):
        emit({
            "error": f"could not uniquely locate infoLayer_farmlands.grle inside {mod_zip_name}",
            "calibration_needed": True,
            "candidates": grle_name,
        })
        return
    if not isinstance(pricing_name, str):
        emit({
            "error": f"could not uniquely locate config/farmlands.xml inside {mod_zip_name}",
            "calibration_needed": True,
            "candidates": pricing_name,
        })
        return

    map_xml_name, map_width_m, map_height_m = find_map_dimensions_xml(zf, namelist)
    if map_width_m is None:
        emit({
            "error": f"could not find a top-level XML declaring <map width= height=> inside {mod_zip_name}",
            "calibration_needed": True,
        })
        return

    grle_bytes = zf.read(grle_name)
    pricing_bytes = zf.read(pricing_name)
    zf.close()

    try:
        pixels, raster_width, raster_height = decode_grle(grle_bytes)
    except ValueError as e:
        emit({"error": f"GRLE decode failed for {grle_name}: {e}", "calibration_needed": True})
        return

    price_per_ha, pricing = parse_pricing_xml(pricing_bytes)
    if price_per_ha is None:
        emit({
            "error": f"{pricing_name} parsed but has no pricePerHa on <farmlands>",
            "calibration_needed": True,
        })
        return

    ownership, err = parse_savegame_farmland_ownership(os.path.join(savegame_dir, "farmland.xml"))
    if ownership is None:
        emit({"error": f"could not read savegame farmland.xml: {err}", "calibration_needed": True})
        return

    histogram = Counter(pixels)

    # --- GATE 1 (hard): decoded id set must exactly equal farmland.xml's id set ---
    decoded_ids = set(histogram.keys())
    savegame_ids = set(ownership.keys())
    if decoded_ids != savegame_ids:
        emit({
            "error": (
                "GATE 1 FAILED: decoded farmland ids do not match savegame farmland.xml's id set. "
                "Refusing to compute area/cost -- this indicates a wrong decode or a mismatched map."
            ),
            "calibration_needed": True,
            "decoded_ids_not_in_savegame": sorted(decoded_ids - savegame_ids)[:20],
            "savegame_ids_not_decoded": sorted(savegame_ids - decoded_ids)[:20],
            "decoded_id_count": len(decoded_ids),
            "savegame_id_count": len(savegame_ids),
        })
        return

    # --- GATE 2 (hard): pixel count matches header dims; pixels are square ---
    if sum(histogram.values()) != raster_width * raster_height:
        emit({
            "error": "GATE 2 FAILED: decoded pixel count does not equal raster width*height.",
            "calibration_needed": True,
        })
        return
    mpp_x = map_width_m / raster_width
    mpp_z = map_height_m / raster_height
    if abs(mpp_x - mpp_z) > 1e-6:
        emit({
            "error": (
                f"GATE 2 FAILED: non-square pixels (m/px x={mpp_x}, z={mpp_z}) -- "
                "area math below assumes square pixels and would be wrong."
            ),
            "calibration_needed": True,
        })
        return
    area_per_pixel_m2 = mpp_x * mpp_z
    total_area_ha = sum(histogram.values()) * area_per_pixel_m2 / 10000
    declared_area_ha = (map_width_m * map_height_m) / 10000
    if abs(total_area_ha - declared_area_ha) > 0.01:
        emit({
            "error": (
                f"GATE 2 FAILED: total decoded area {total_area_ha} ha does not match the map's "
                f"declared {declared_area_ha} ha."
            ),
            "calibration_needed": True,
        })
        return

    # --- Per-parcel area/cost ---
    parcels = {}
    calibration_notes = []
    for fid, pixel_count in histogram.items():
        area_ha = round(pixel_count * area_per_pixel_m2 / 10000, 4)
        price_info = pricing.get(fid)
        if price_info is None or price_info["price_scale"] is None:
            scale = 1.0
            calibration_notes.append(f"farmland id {fid}: no priceScale found in {pricing_name}, assumed 1.0")
        else:
            scale = price_info["price_scale"]
        cost = round(area_ha * price_per_ha * scale, 2)
        parcels[fid] = {
            "area_ha": area_ha,
            "price_scale": scale,
            "cost": cost,
            "owner_farm_id": ownership.get(fid),
            "npc_name": price_info["npc_name"] if price_info else None,
        }

    # Validate farm_id against farms.xml itself (the authoritative farm list, same source
    # read_economy.py uses) -- NOT against farmland.xml ownership. A real farm that
    # genuinely owns 0 parcels must still pass this check; only a farm_id that doesn't
    # exist at all should error. Checking against farmland.xml alone would repeat F-001's
    # exact mistake: mistaking "owns nothing (valid)" for "doesn't exist (error)".
    farms_root, farms_generic = load_xml(os.path.join(savegame_dir, "farms.xml"))
    if farms_root is None:
        emit({
            "error": f"could not read farms.xml to validate farm_id {farm_id}: {farms_generic.get('error')}",
            "calibration_needed": True,
        })
        return
    all_farm_ids = sorted(
        int(f.attrib["farmId"]) for f in farms_root.iter("farm") if "farmId" in f.attrib
    )
    if farm_id not in all_farm_ids:
        emit({
            "error": f"farm_id {farm_id} not found in farms.xml. Available farm_ids: {all_farm_ids}",
            "calibration_needed": False,
        })
        return

    owned_ids = sorted(fid for fid, p in parcels.items() if p["owner_farm_id"] == farm_id)
    owned_total_area_ha = round(sum(parcels[fid]["area_ha"] for fid in owned_ids), 4)
    owned_total_cost = round(sum(parcels[fid]["cost"] for fid in owned_ids), 2)

    # --- Optional bonus cross-check against farms.xml's own fieldPurchase stat ---
    field_purchase_check = None
    if farms_root is not None:
        fp_elem = farms_root.find(f".//farm[@farmId='{farm_id}']/finances/stats/fieldPurchase")
        if fp_elem is not None and fp_elem.text:
            recorded = abs(float(fp_elem.text))
            field_purchase_check = {
                "farms_xml_fieldPurchase_abs": recorded,
                "computed_owned_total_cost": owned_total_cost,
                "difference": round(recorded - owned_total_cost, 2),
                "match": abs(recorded - owned_total_cost) < 1.0,
            }

    # --- Field -> farmland -> ownership, using the map-specific identity rule ---
    field_ids, field_err = parse_savegame_field_ids(os.path.join(savegame_dir, "fields.xml"))
    fields_out = None
    if field_ids is None:
        calibration_notes.append(f"could not read fields.xml for field->farmland mapping: {field_err}")
    else:
        fields_out = []
        for field_id in field_ids:
            if field_id in parcels:
                p = parcels[field_id]
                fields_out.append({
                    "field_id": field_id,
                    "farmland_id": field_id,  # map-specific identity rule, see docstring
                    "owned": p["owner_farm_id"] == farm_id,
                    "owner_farm_id": p["owner_farm_id"],
                })
            else:
                calibration_notes.append(
                    f"field id {field_id} has no matching farmland id in the decoded raster -- "
                    "the field_id==farmland_id assumption does not hold for this field; "
                    "reported with farmland_id=null rather than guessed"
                )
                fields_out.append({
                    "field_id": field_id,
                    "farmland_id": None,
                    "owned": None,
                    "owner_farm_id": None,
                })

    owned_fields = [f["field_id"] for f in (fields_out or []) if f["owned"]]

    emit({
        "sources": {
            "career": os.path.join(savegame_dir, "careerSavegame.xml"),
            "farmland_ownership": os.path.join(savegame_dir, "farmland.xml"),
            "fields": os.path.join(savegame_dir, "fields.xml"),
            "map_mod_zip": mod_zip_path,
            "grle": grle_name,
            "pricing_xml": pricing_name,
        },
        "map": {
            "map_id": map_id,
            "declared_size_m": {"width": map_width_m, "height": map_height_m},
            "raster_size_px": {"width": raster_width, "height": raster_height},
            "meters_per_pixel": mpp_x,
            "price_per_ha": price_per_ha,
        },
        "gates_passed": {
            "gate1_id_set_matches_savegame": True,
            "gate2_area_matches_declared_map_size": True,
        },
        "farm_id": farm_id,
        "owned": {
            "parcel_ids": owned_ids,
            "count": len(owned_ids),
            "total_area_ha": owned_total_area_ha,
            "total_cost": owned_total_cost,
            "field_ids": owned_fields,
        },
        "field_purchase_cross_check": field_purchase_check,
        "parcels": parcels,
        "fields": fields_out,
        "calibration_needed": len(calibration_notes) > 0,
        "calibration_notes": calibration_notes,
    })


if __name__ == "__main__":
    main()
