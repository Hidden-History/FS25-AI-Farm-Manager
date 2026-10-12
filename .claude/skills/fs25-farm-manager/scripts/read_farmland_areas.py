"""
Decode the map's infoLayer_farmlands.grle raster to get real per-parcel area
(hectares), cost, and a field-number -> farmland-id -> owner mapping.

Usage: python3 read_farmland_areas.py <savegame_dir> [mods_dir] [--farm-id N]
                                       [--mods-dir PATH] [--config PATH]
    (run with --help for the full argparse usage; unknown flags are an error,
    not silently ignored)
    --farm-id N     Which farmId counts as "owned" (default: 1).
    --mods-dir PATH Where the map mod lives. If omitted (and no positional
                    mods_dir is given either), resolved from --config's
                    config.json, else a walk-up looking for
                    sanctum/config.json -> paths.mods_dir -- same lookup
                    read_fields.py's find_mods_dir() uses, reused here rather
                    than reinvented, so both scripts agree on where mods live.
    --config PATH   Where that config.json is. If omitted, this script walks
                    up from its own directory (item #12: that walk-up assumes
                    a per-project install and cannot resolve on a personal
                    one -- pass --config there).

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

CROSS-CHECK AGAINST farms.xml's OWN <fieldPurchase> -- PRESENT BUT DISABLED.
The strongest corroboration this decode ever had was the farm's own recorded
land spend agreeing with the computed parcel total to the cent. That read is
DEFECTIVE as shipped (BUG-014: `find` returns slot 0 of a multi-slot
`<stats>` window) and `farms_xml_fieldPurchase_abs` is a blocked field, so
per DEC-057 (9) the cross-check ships DISABLED, not deleted -- see
CROSS_CHECK_ENABLED below. The corrected read lives in
read_field_purchase_window() and is unit-tested; nothing calls it at runtime.

⚠ NO FIGURE FROM THIS SAVE IS PINNED IN THIS DOCSTRING, AND THAT IS DEC-059,
NOT TIDINESS. This section used to quote "18 owned parcels", "$15,741,096.00"
and a literal `<fieldPurchase>` value as evidence the decode was right. Every
one of those went stale as soon as the player bought land -- re-measured
2026-08-05, the same save reports a different parcel count and a different
slot-0 value. A docstring is trusted exactly like code, so a pinned figure
there is the same defect as a pinned figure in a test. What is durable is the
METHOD -- the gates above, which are recomputed every run and refuse to
produce numbers when they fail. Read the gate output, not this prose.

===========================================================================
3. FIELD -> FARMLAND MAPPING -- A MEASURED SPATIAL JOIN (TECH-DEBT-095, HIGH)
===========================================================================
The savegame carries NO field->farmland link. Re-measured 2026-08-05: every
`<field>` in fields.xml has `id` plus fourteen crop-state attributes
(fruitType, growthState, weedState, ...) and NOTHING ELSE -- no area, no
position, no farmland reference, no child elements.

⛔ A FALSE ENGINE CLAIM WAS REMOVED FROM THIS DOCSTRING 2026-08-07. It read
that "a farmland answers `getField()`", cited to `FarmlandManager.md`.
`Farmland:getField` DOES NOT EXIST: at FS25 Community LUADOC @ 86f08357778f,
`docs/script/Economy/Farmland.md` (coverage.complete: true) declares exactly
five functions -- delete, load, new, setArea, setIndicatorPosition -- and none
is `getField`. The corpus's only `getField` is `AbstractFieldMission:getField()`,
a MISSION-scoped class, so it answers the join only for fields under contract
and is not a general accessor.

What the engine actually does: `getFarmlandIdAtWorldPosition` is its general
answer to this question, and it consumes a WORLD POSITION. This script is an
offline parser with no `g_farmlandManager`, so it cannot CALL that accessor --
but the map's own `map.i3d` authors every field as a polygon in the same
world-coordinate space that accessor consumes (a "fields" scene-graph node,
one child per field, each holding a point-container of vertices), and
infoLayer_farmlands.grle is the exact raster that accessor samples. So this
script REPLICATES the engine's own read, offline: decode the polygon, find
its own area centroid (polygon_area_centroid), transform world -> raster via
the engine's own convertWorldToLocalPosition formula (CITE_WORLD_TO_RASTER,
cited from FS25 Community LUADOC), and sample the same raster gate 1/gate 2
already validated (sample_farmland_id).

⛔ UNTIL 2026-09-04 THIS WAS AN ASSUMPTION -- `field_id == farmland_id`,
licensed by the retired ruling ARCH-R3-04, scoped to one map, derived once
from an external AutoDrive_config.xml and never re-derived per run. It is
GONE, not patched: TECH-DEBT-095 (HIGH) measured it FALSE on MapUS/
savegame3 (the map's own field ids and the save's overlap 64/77, with 13 on
each side the other lacks -- oversight/reports/VERIFY-plan-field-resolver-
premises-2026-09-04.md sec. 3.1), and the identity guard could never fire on
a map where the id spaces happen to be a subset of each other regardless of
whether the correspondence was real.

ARCH-R3-06 replaces it (build_arch_r3_06). Unlike its predecessor its AREA
claim is falsifiable per save. ⚠ ITS JOIN CLAIM IS NOT (TECH-DEBT-107): both
corroborations carried in the same object are silent about WHERE a polygon
sits -- the shoelace sum is invariant under rotation and translation, and
field_coverage compares id SETS, never geometry. The two carried are:
`field_coverage` (do the map's and the save's field ids form the same set?
build_field_coverage) and `shoelace_label_check` (does this parser's own
polygon-area formula -- item 3, shoelace_area_ha -- reproduce the map
author's own printed `<Note text="fieldN\\nN.NN ha"/>` label? verified on
this build: 0/175 mismatches across savegame1/Montana and savegame2/
LoneStar, and 0/77 on MapUS). A single centroid sample still cannot see a
field that genuinely straddles two farmland parcels -- every vertex is also
sampled, and `straddles_farmland` flags that case on the affected row rather
than silently picking a side.

(This is the mistake the engine's own naming invites and that shipped mods
make: `AbstractFieldMission:getFarmlandId()` returns `field:getId()`, and
FS25_YieldTracker puts `getFarmlandIdAtWorldPosition`'s farmland id in a
variable named `fieldID` while indexing `g_fieldManager.fields[...]` with a
field id elsewhere -- one name, two id spaces, all the way to its UI.)

===========================================================================
Output contract:
    - Never returns [] / {} / a best-effort guess. If a hard gate fails,
      emits {"error": "...", "calibration_needed": true} and STOPS before
      computing any area/cost number.
    - calibration_needed means "could not confidently locate/validate the
      data" -- not "a parcel has 0 hectares" (that would be a real, valid
      result if it ever occurred).
    - Emits the sec. 6.2 domain envelope, PLUS a legacy top-level block for
      read_fields.py. See LEGACY_TOP_LEVEL_SHIM below for why both, and for
      the condition that retires the second.
"""
import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit, finite_number

# ---------------------------------------------------------------- sec. 6.2 --
SCHEMA_VERSION = 1
DOMAIN = "land"
SET = "land"
GENERATOR = "read_farmland_areas.py"
GENERATOR_VERSION = "3.0.0"
CAPABILITY_IDS = ("b13", "b14")

SECTION_MAP = "map_calibration"
SECTION_PARCELS = "farmland_parcels"
SECTION_OWNED = "owned_land"
SECTION_FIELDS = "field_ownership"

# TECH-DEBT-095 (HIGH). ARCH-R3-04's `field_id == farmland_id` identity
# assumption -- permanently unfalsifiable, scoped to one map -- is RETIRED,
# not patched. It was measured false on MapUS/savegame3: the map's own field
# polygons and the save's own field ids overlap 64/77, with 13 on each side
# the other lacks (oversight/reports/VERIFY-plan-field-resolver-premises-
# 2026-09-04.md sec. 3.1). Replaced below by a MEASURED spatial join --
# ARCH-R3-06 -- that samples infoLayer_farmlands.grle at each field polygon's
# own area centroid (map.i3d), instead of assuming the ids coincide.
SPATIAL_JOIN_BASIS = "spatial_centroid_raster_join"

# fs25-lookup, FS25 Community LUADOC @24afb18e7cfb788b7686b9ec791671e0dcba32b9,
# docs/script/Economy/FarmlandManager.md, function convertWorldToLocalPosition
# (emit-clean, no repair applied -- quoted verbatim):
#     math.floor(localMapWidth  * (worldPosX + terrainSize*0.5) / terrainSize)
#     math.floor(localMapHeight * (worldPosZ + terrainSize*0.5) / terrainSize)
# Applied per-axis below using this map's own declared width/height in place
# of a single terrainSize -- gate 2 already requires them equal within
# tolerance (square pixels), so this is the same formula, not a new one.
CITE_WORLD_TO_RASTER = (
    "FS25 Community LUADOC @24afb18e7cfb788b7686b9ec791671e0dcba32b9, "
    "docs/script/Economy/FarmlandManager.md, function "
    "convertWorldToLocalPosition (emit-clean, no repair applied): "
    "math.floor(localMapWidth * (worldPosX + terrainSize*0.5) / terrainSize), "
    "math.floor(localMapHeight * (worldPosZ + terrainSize*0.5) / terrainSize). "
    "Applied per-axis with this map's own declared width/height in place of "
    "a single terrainSize."
)

# ⛔ DEC-057 (9). The farms.xml <fieldPurchase> cross-check ships DISABLED,
# NOT DELETED. Two things follow, and both are the point:
#   1. The blocked path is NOT READ AT RUNTIME. Nothing calls
#      read_field_purchase_window() while this is False, so the land sections'
#      source_elements honestly omit farms.xml:farm/finances/stats/fieldPurchase
#      and sec. 6.8.2 tooth 1 never applies to this domain.
#   2. The corrected read still exists and is still tested. BUG-014's defect is
#      fixed here rather than left shipping behind a deletion, so DEFER-014 can
#      restore the cross-check by flipping this one flag once the field is
#      unblocked -- which is a registry decision, not this script's.
# Flipping this to True WITHOUT unblocking farms_xml_fieldPurchase_abs is a
# tooth-2 violation. The land suite proves that rather than trusting it.
CROSS_CHECK_ENABLED = False

# The legacy top-level block this script emits ALONGSIDE the sec. 6.2 envelope.
# read_fields.py:251-266 (frozen contract, never-edit) reads top-level
# `gates_passed`, `owned.field_ids`, `owned.total_area_ha` and
# `field_purchase_cross_check`; the envelope moves all of those under
# `sections.*`, so migrating without this shim breaks that consumer.
#
# ⚠ RETIREMENT CONDITION, STATED SO THIS DOES NOT BECOME ARCHITECTURE: the shim
# retires when item 10 migrates read_fields.py onto the envelope. Delete
# build_legacy_top_level() and its test at that point, not before.
#
# It is DERIVED from the section data and never computed a second time -- two
# independent computations of one number is how the two views drift apart, and
# a test asserts they agree.
LEGACY_TOP_LEVEL_SHIM = True


def find_mods_dir(explicit, config_path=None):
    """Locate the mods dir: the flag/positional arg, else --config's
    config.json, else a walk-up looking for sanctum/config.json ->
    paths.mods_dir. Same lookup as read_fields.py's find_mods_dir() -- kept
    as a separate copy (not imported) so this script has no import-time
    dependency on read_fields.py, but the logic and error wording are meant to
    match so the two scripts never disagree about where mods live.

    ⚠ THE --config BRANCH'S WORDING MUST MATCH read_fields.py's COPY OF THIS
    FUNCTION BYTE FOR BYTE (item #12). If you change one, change both.

    Returns (path_or_None, how_or_reason)."""
    if explicit:
        if not os.path.isdir(explicit):
            return None, f"mods_dir {explicit!r} is not a directory"
        return explicit, "explicit mods_dir (positional or --mods-dir)"
    if config_path:
        if not os.path.isfile(config_path):
            return None, f"--config {config_path!r} does not exist"
        try:
            with open(config_path) as f:
                paths = (json.load(f).get("paths") or {})
            md = paths.get("mods_dir")
        except (OSError, json.JSONDecodeError) as e:
            return None, f"found {config_path} but could not read paths.mods_dir: {e}"
        if not md:
            return None, f"{config_path} has no paths.mods_dir"
        if not os.path.isdir(md):
            return None, f"paths.mods_dir {md!r} from --config {config_path!r} is not a directory"
        return md, f"--config {config_path!r} -> paths.mods_dir"
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


def find_install_dir(explicit, config_path=None):
    """Locate the FS25 game install dir: the flag, else --config's
    config.json, else the same sanctum/config.json walk-up find_mods_dir()
    uses above -- deliberately mirrored rather than shared, for the same
    reason find_mods_dir()'s own docstring gives: no import-time coupling
    between sibling scripts, wording kept in sync by hand.

    TECH-DEBT-103b. A MOD map never needs this -- it is only consulted as a
    fallback when the mod-zip lookup in main() fails, to resolve a BASE-GAME
    map that ships no zip at all (e.g. MapUS). Unresolved is reported, never
    guessed: no hardcoded Windows/WSL path (FRICTION-LOG.md F-007) -- this
    would be baked into a PUBLIC mod and wrong on every machine but the one
    it was written on.

    Returns (path_or_None, how_or_reason)."""
    if explicit:
        if not os.path.isdir(explicit):
            return None, f"install_dir {explicit!r} is not a directory"
        return explicit, "explicit install_dir (--install-dir)"
    if config_path:
        if not os.path.isfile(config_path):
            return None, f"--config {config_path!r} does not exist"
        try:
            with open(config_path) as f:
                paths = (json.load(f).get("paths") or {})
            idir = paths.get("install_dir")
        except (OSError, json.JSONDecodeError) as e:
            return None, f"found {config_path} but could not read paths.install_dir: {e}"
        if not idir:
            return None, f"{config_path} has no paths.install_dir"
        if not os.path.isdir(idir):
            return None, f"paths.install_dir {idir!r} from --config {config_path!r} is not a directory"
        return idir, f"--config {config_path!r} -> paths.install_dir"
    here = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        cfg = os.path.join(here, "sanctum", "config.json")
        if os.path.isfile(cfg):
            try:
                with open(cfg) as f:
                    paths = (json.load(f).get("paths") or {})
                idir = paths.get("install_dir")
            except (OSError, json.JSONDecodeError) as e:
                return None, f"found {cfg} but could not read paths.install_dir: {e}"
            if not idir:
                return None, f"{cfg} has no paths.install_dir"
            if not os.path.isdir(idir):
                return None, f"paths.install_dir {idir!r} from config.json is not a directory"
            return idir, "sanctum/config.json -> paths.install_dir"
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None, "no sanctum/config.json found above this script, and no install_dir given"


def find_base_game_map_dir(install_dir, map_id):
    """The base-game map directory for a `mapId` that has no mod-zip form.

    ⚠ CASE-INSENSITIVE, AND MEASURED WHY: the savegame's careerSavegame.xml
    reports mapId 'MapUS'; the on-disk directory is 'mapUS' (measured
    2026-09-03, <install_dir>/data/maps/mapUS/) -- an exact-case match would
    silently fail on the very map this fallback exists for.

    ⚠ MATCHED ON THE FULL DIRECTORY NAME ONLY, never a substring or prefix --
    the F-019 rule ("resolve the path, never the basename") applied to a
    directory instead of a file: a fuzzy match here could resolve a genuinely
    different base-game map and publish a confidently wrong farmland raster.

    Returns (path_or_None, reason_or_None)."""
    maps_root = os.path.join(install_dir, "data", "maps")
    if not os.path.isdir(maps_root):
        return None, f"{maps_root} is not a directory"
    target = map_id.lower()
    try:
        entries = os.listdir(maps_root)
    except OSError as e:
        return None, f"could not list {maps_root}: {e}"
    matches = [d for d in entries
              if d.lower() == target and os.path.isdir(os.path.join(maps_root, d))]
    if not matches:
        return None, f"no directory named {map_id!r} (case-insensitive) under {maps_root}"
    if len(matches) > 1:
        return None, (
            f"{len(matches)} directories under {maps_root} match {map_id!r} "
            f"case-insensitively: {sorted(matches)} -- refusing to guess which one")
    return os.path.join(maps_root, matches[0]), None


def _dir_namelist(root_dir):
    """The on-disk equivalent of ZipFile.namelist() for a base-game map
    directory -- SCOPED to where the files this script reads actually live,
    not a full recursive walk.

    A base-game map directory also carries textures/, sounds/, envMaps/,
    guidedTour/, licensePlates/ and missions/ siblings of config/ and data/
    that this script has no use for and that a full walk would pay to
    enumerate for nothing (measured: mapUS/data/ alone is 24MB across 110
    entries; the sibling asset directories are considerably larger). Root-
    level files cover the map's own declaring XML; config/ and data/ are
    walked recursively to match the depth a mod zip's own internal layout can
    carry (mods routinely wrap their content in one extra folder --
    'mapUS/config/farmlands.xml' inside the installed FS25_Montana_4X.zip,
    confirmed 2026-09-03 -- so this must tolerate that depth too, not assume
    either shape)."""
    names = []
    try:
        entries = os.listdir(root_dir)
    except OSError:
        return names
    for entry in entries:
        if os.path.isfile(os.path.join(root_dir, entry)):
            names.append(entry)
    for sub in ("config", "data"):
        sub_root = os.path.join(root_dir, sub)
        if not os.path.isdir(sub_root):
            continue
        for dirpath, _dirs, files in os.walk(sub_root):
            rel_dir = os.path.relpath(dirpath, root_dir)
            for fn in files:
                names.append((f"{rel_dir}/{fn}" if rel_dir != "."
                             else fn).replace(os.sep, "/"))
    return names


class _DirEntries:
    """Duck-types the subset of zipfile.ZipFile this script actually calls
    (.namelist, .read, .close) over a plain directory, so a base-game map --
    which ships as files on disk, never a zip -- can be searched and read by
    find_zip_entry() / find_map_dimensions_xml() and by main()'s own
    zf.read() calls exactly like a mod's zip contents, with none of that
    downstream code needing to know which kind of source it got."""

    def __init__(self, root_dir):
        self.root_dir = root_dir
        self._names = _dir_namelist(root_dir)

    def namelist(self):
        return self._names

    def read(self, relpath):
        with open(os.path.join(self.root_dir, relpath), "rb") as f:
            return f.read()

    def close(self):
        pass


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
    top-level .xml files for the tag.

    ⚠ TECH-DEBT-103b WIDENED THIS FROM count("/") == 1 TO <= 1. A mod zip
    routinely wraps its content in one extra folder (confirmed 2026-09-03:
    'mapUS/mapUS.xml' inside the installed FS25_Montana_4X.zip -- 1 slash).
    A BASE-GAME map directory carries no such wrapper -- its own declaring
    XML sits at 0 slashes ('mapUS.xml' directly under
    <install_dir>/data/maps/mapUS/, confirmed the same day). Widening rather
    than branching on source kind: this function does not need to know which
    kind of source it was handed, only how deep to look."""
    candidates = [n for n in namelist if n.count("/") <= 1 and n.lower().endswith(".xml")]
    for name in candidates:
        try:
            text = zf.read(name).decode("utf-8", errors="ignore")
        except (KeyError, zipfile.BadZipFile, OSError):
            continue
        m = re.search(r'<map\s[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', text)
        if m:
            return name, float(m.group(1)), float(m.group(2))
    return None, None, None


def find_map_i3d_entry(namelist, map_xml_name):
    """TECH-DEBT-095. The map's own field-bearing i3d, found by matching its
    BASENAME to the already-located map XML's basename: 'mapUS/mapUS.xml' ->
    'mapUS/mapUS.i3d' (Montana, and the base game); 'config/map.xml' ->
    'map.i3d' (Lone Star Plains -- a DIFFERENT directory, same basename).
    Verified against all three maps this project has real files for; never
    assumed same-directory, because Lone Star's own config/map.xml sits one
    folder away from the root-level map.i3d it declares.

    Depth-restricted to <=1 slash (mirrors find_map_dimensions_xml's own
    rule for the map's declaring XML) and refuses to guess if more than one
    entry shares that basename at that depth."""
    if not map_xml_name:
        return None, "no map xml located; cannot locate its i3d"
    stem = os.path.splitext(os.path.basename(map_xml_name))[0] + ".i3d"
    matches = [n for n in namelist
              if n.count("/") <= 1 and os.path.basename(n) == stem]
    if not matches:
        return None, f"no <=1-deep .i3d entry named {stem!r} found"
    if len(matches) > 1:
        return None, (f"{len(matches)} entries named {stem!r} found: {matches} "
                      "-- refusing to guess which one")
    return matches[0], None


def parse_pricing_xml(xml_bytes):
    """Parse the map's config/farmlands.xml -> (price_per_ha, {id: (priceScale, npcName)}).

    ⛔ TECH-DEBT-103. `Farmland:load` (FS25 Community LUADOC @ 24afb18e7cf,
    docs/script/Economy/Farmland.md, function `load`, emit-repaired) reads TWO
    mutually exclusive forms per parcel:
        self.fixedPrice = xmlFile:getValue(key .. "#price")
        if self.fixedPrice == nil then
            self.priceFactor = xmlFile:getValue(key .. "#priceScale", 1)
        end
        self.price = self.fixedPrice or 1
        self:updatePrice()
    A parcel that declares `price=` gets `fixedPrice`; `priceScale` is only
    consulted when `price=` is ABSENT. `updatePrice()`'s body is not one of
    Farmland.md's five documented functions (delete, load, new, setArea,
    setIndicatorPosition), so what it does with `fixedPrice` is undocumented
    here -- this parser has never computed that form and does not start now.
    `fixed_price_declared` records only the ATTRIBUTE'S PRESENCE so the caller
    can refuse to publish the derived (priceScale) figure for that parcel --
    see the sensor in main()'s per-parcel loop and compute_owned_totals()."""
    root = ET.fromstring(xml_bytes)
    farmlands_elem = root.find("farmlands")
    if farmlands_elem is None:
        return None, {}
    # TECH-DEBT-108: finite_number, not float(). These two attributes are the
    # ONLY inputs to land_value, which is what the manager actually reads, and
    # a nan here propagates through the multiplication into the land envelope's
    # JSON as a bare `NaN` -- invalid JSON, failing a strict consumer on the
    # whole document. None means "no usable figure" and is already the value
    # this parser reports for an absent attribute, so downstream refusal paths
    # are the existing ones rather than new ones.
    price_per_ha = finite_number(farmlands_elem.attrib.get("pricePerHa"))
    pricing = {}
    for fl in farmlands_elem.findall("farmland"):
        try:
            fid = int(fl.attrib["id"])
        except (KeyError, ValueError):
            continue
        pricing[fid] = {
            # TECH-DEBT-108, same reason as pricePerHa above.
            "price_scale": finite_number(fl.attrib.get("priceScale")),
            "npc_name": fl.attrib.get("npcName"),
            # TECH-DEBT-103: presence only, per Farmland:load above -- never
            # coerced to a number, because this parser does not compute the
            # fixedPrice form and must not imply it read a value it did not use.
            "fixed_price_declared": fl.attrib.get("price") is not None,
        }
    return price_per_ha, pricing


# ⚖ ARCH-R3-05's falsifier, and it must read the RAW ATTRIBUTE TEXT.
# Spec § 6.5 rev 10: "reading the coerced value re-runs the derivation the check
# exists to test and cannot fail." So this is matched against the string as it
# sits in the file, BEFORE any int().
RAW_ID_TEXT = re.compile(r"^-?[0-9]+$")


def build_raw_id_conformance(root):
    """ARCH-R3-05 is falsified by ONE non-integer @id or @farmId, and can never
    be confirmed -- a census is induction, never a citation (spec § 6.5).

    So what is reported is whether the FALSIFIER FIRED, not whether it ran.
    Spec § 6.5 fixes the three values and they are not interchangeable: True
    where a test exists and it fired -- this save CONTRADICTS the ruling;
    False where a test exists and it did not fire; None where there was
    nothing to test. NEVER False by default -- the spec is explicit that an
    untaken measurement is `null`.

    ⚠ `True if checked else None` is the defect this replaced (S1). It reports
    that the check RAN, which is non-zero on every real save, so the field was
    constant `true` and read as "the save contradicts ARCH-R3-05" beside a
    `holds: True` saying it does not -- the same object asserting both.

    ⚠ This deliberately does NOT read through parse_savegame_farmland_ownership's
    `except (KeyError, ValueError): continue`. A row whose id fails to coerce is
    dropped there (spec § 6.5 names this an RSK-001 shape and says the ruling
    "does not license that `continue`"), so a falsifier reading post-coercion
    rows could never see the very value that would refute the ruling. It reads
    every <farmland> element's raw attributes instead."""
    checked = 0
    nonconforming = []
    for fl in root.iter("farmland"):
        for attr in ("id", "farmId"):
            raw = fl.attrib.get(attr)
            if raw is None:
                continue
            checked += 1
            if not RAW_ID_TEXT.match(raw):
                nonconforming.append("farmland@%s=%r" % (attr, raw))
    return {
        "rule": "every farmlands/farmland @id and @farmId matches ^-?[0-9]+$ "
                "as RAW TEXT, before coercion",
        "raw_values_checked": checked,
        "nonconforming": nonconforming,
        "holds": not nonconforming if checked else None,
        # None, never False, where nothing was measured (spec § 6.5 rev 10).
        # DERIVED FROM THE DATA, the same shape ARCH-R3-06's own
        # falsifiable_on_this_save uses (build_arch_r3_06): true exactly
        # where the check found a contradiction, never merely where it was
        # able to look.
        "falsifiable_on_this_save": bool(nonconforming) if checked else None,
        "note": ("ARCH-R3-05 can be falsified by one non-integer value and can "
                 "never be confirmed: extending this census over more saves is "
                 "induction, not a declaration of type."),
    }


def parse_savegame_farmland_ownership(path):
    """Parse savegame farmland.xml -> {id: farmId}.

    Returns (dict, error_or_None, raw_id_conformance_or_None). The third value
    is ARCH-R3-05's per-save falsifier -- see build_raw_id_conformance."""
    root, generic = load_xml(path)
    if root is None:
        return None, generic.get("error"), None
    conformance = build_raw_id_conformance(root)
    ownership = {}
    for fl in root.iter("farmland"):
        try:
            fid = int(fl.attrib["id"])
            owner = int(fl.attrib["farmId"])
        except (KeyError, ValueError):
            continue
        ownership[fid] = owner
    if not ownership:
        return (None,
                "farmland.xml parsed but contained no <farmland id=... farmId=...> elements",
                conformance)
    return ownership, None, conformance


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


def parse_current_day(savegame_dir):
    """environment.xml's <currentDay>, or (None, reason).

    Used ONLY to report whether the stored <stats> window reaches the present
    day. It never feeds a money figure -- see read_field_purchase_window()."""
    root, generic = load_xml(os.path.join(savegame_dir, "environment.xml"))
    if root is None:
        return None, generic.get("error")
    elem = root.find("currentDay")
    if elem is None or not (elem.text or "").strip():
        return None, "environment.xml has no <currentDay>"
    try:
        return int(elem.text.strip()), None
    except ValueError:
        return None, f"environment.xml <currentDay> is not an integer: {elem.text.strip()!r}"


def read_field_purchase_window(farms_root, farm_id, current_day):
    """BUG-014. Sum EVERY <finances><stats day=N><fieldPurchase>, and report
    how much of the farm's life that window actually covers.

    ⛔ THE DEFECT THIS REPLACES: `farms_root.find(".//farm[...]/finances/stats/
    fieldPurchase")` returns the FIRST match, so a five-slot window shipped
    SLOT 0 ALONE under the name `farms_xml_fieldPurchase_abs`, which promises a
    lifetime absolute. It answered "what did I spend during stored period 0" --
    a question nothing asked.

    ⛔ AND THE NAIVE FIX IS ALSO WRONG, WHICH IS WHY COVERAGE IS RETURNED
    RATHER THAN ASSUMED. findall-and-sum silently UNDER-REPORTS lifetime spend
    on any save whose stored window has rolled. The live save is exactly that
    case -- environment.xml reads currentDay=10 while only five slots (day 0-4)
    exist -- and the under-report would look like a fresh cross-check failure
    with nothing actually wrong. BUG-014 sec. 6 condition 4: whether the window
    can roll is UNTESTED in general and LUADOC documents no retention policy
    for savegame finance stats (probed across four query shapes, 0 matched).

    So `covers_full_history` is deliberately the string "unknown", never a
    bool. We can prove the window does NOT reach the current day; we can never
    prove from the savegame alone that it covers the farm's whole life. A bool
    would have to lie in one direction or the other -- DEC-001's rule, applied
    to a claim rather than to a container.

    Returns a dict; the caller decides whether it may be emitted (it may not,
    while farms_xml_fieldPurchase_abs is blocked -- see CROSS_CHECK_ENABLED)."""
    slots = []
    for stats in farms_root.findall(f".//farm[@farmId='{farm_id}']/finances/stats"):
        elem = stats.find("fieldPurchase")
        if elem is None or not (elem.text or "").strip():
            continue
        try:
            value = float(elem.text.strip())
        except ValueError:
            # Never silently skip a malformed money value into a sum -- a
            # dropped slot IS an under-report, the exact harm above.
            return {"error": "farms.xml has a non-numeric <fieldPurchase>: "
                             f"{elem.text.strip()!r}"}
        day = stats.attrib.get("day")
        # ⛔ A MISSING `day` CORRUPTS THE COVERAGE SIGNAL IDENTICALLY TO A
        # MALFORMED ONE, and only the malformed path was closed. `day = None`
        # was appended silently, so latest_slot_day, window_reaches_current_day
        # and covers_full_history -- the entire claim ABOUT the money sum --
        # degraded while the sum itself stayed right. The branch below refuses a
        # non-integer day for exactly this reason; absence is not the safer case
        # of the two, it is the quieter one. test_S7 exercised only "notaday".
        if day is None:
            return {"error": "farms.xml has a <stats> element with no `day` "
                             "attribute -- refusing to report a coverage window "
                             "over a slot whose day is unknown"}
        try:
            day = int(day)
        except ValueError:
            # Never silently swallow a malformed day into None. The money sum
            # would stay correct while latest_slot_day,
            # window_reaches_current_day and covers_full_history -- the entire
            # coverage signal ABOUT that sum -- silently corrupt. That is
            # DEC-001's rule applied to a claim rather than to a container, and
            # it is what the adjacent value branch above already does.
            return {"error": "farms.xml has a non-integer <stats day>: "
                             f"{stats.attrib.get('day')!r}"}
        slots.append({"day": day, "field_purchase": value})

    if not slots:
        # Absence must fail, never a quiet zero. A farm that bought no land is
        # not the same fact as a <stats> window we could not read, and a 0.0
        # here would be indistinguishable from both.
        return {"error": f"farms.xml holds no <finances><stats><fieldPurchase> "
                         f"for farm {farm_id} -- refusing to report 0 spend"}

    days = sorted(s["day"] for s in slots if s["day"] is not None)
    latest = days[-1] if days else None
    reaches_current_day = (
        None if (latest is None or current_day is None) else latest >= current_day
    )
    return {
        "field_purchase_abs_sum": abs(round(sum(s["field_purchase"] for s in slots), 2)),
        "slots_present": len(slots),
        "slot_days": days,
        "current_day": current_day,
        "latest_slot_day": latest,
        "window_reaches_current_day": reaches_current_day,
        "covers_full_history": "unknown",
        "coverage_note": (
            "Sum of ALL stored slots. Whether the stored window spans the farm's "
            "whole life cannot be determined from the savegame: the engine's "
            "retention policy for <finances><stats> is undocumented (a condition of correcting the "
            "single-period land-cost read). Where window_reaches_current_day is false the "
            "window has demonstrably rolled and this sum is a LOWER BOUND on "
            "lifetime spend, not the total."
        ),
        "per_slot": slots,
    }


M2_PER_HECTARE = 10000


def pixels_to_hectares(pixel_count, area_per_pixel_m2):
    """Raster pixels -> hectares. One conversion, one place.

    ⛔ EXTRACTED FROM main() 2026-08-07 SO IT CAN BE TESTED AT ALL. It was
    inline at two call sites, and NO offline test covered it: the suites
    supplied total_area_ha as a literal and build_sections stored it verbatim,
    so the shim parity test proved the two views read the same slot, not that
    either was right. Changing /10000 to /1000 shipped a 10x wrong area with
    the suite green -- and gate 2 could not catch it either, because gate 2
    uses this same factor on BOTH sides of its comparison, so a consistent
    scale error passes the gate.

    This is the figure the farm's whole debt premise rests on."""
    return pixel_count * area_per_pixel_m2 / M2_PER_HECTARE


def compute_parcel_cost(fid, area_ha, price_per_ha, price_info, pricing_name):
    """One parcel's (cost_or_None, price_scale, calibration_note_or_None).

    ⛔ TECH-DEBT-103, EXTRACTED FROM main()'s per-parcel loop SO IT CAN BE
    TESTED AT ALL -- the same reason pixels_to_hectares was extracted
    2026-08-07. No map available to this project declares a per-parcel
    `price` (measured across all 12 installed maps plus the base game, 2026-
    09-03), so this branch has no real fixture to run against; a synthetic
    one, driven straight at this function, is the only way to prove it has
    teeth.

    See parse_pricing_xml for the Farmland:load citation this sensor rests
    on: a declared `price=` sets fixedPrice and the engine never derives that
    parcel's price from areaInHa*pricePerHa*priceScale, so publishing the
    derived figure for it would be a confident wrong number, not a stale one.
    cost is therefore None -- never the derived float, never 0 -- and
    compute_owned_totals() propagates that absence into the aggregate rather
    than silently summing past it."""
    if price_info is not None and price_info.get("fixed_price_declared"):
        scale = (price_info["price_scale"] if price_info.get("price_scale") is not None
                 else 1.0)
        note = (
            f"farmland id {fid}: declares a per-parcel price= in {pricing_name} -- "
            "Farmland:load reads that into fixedPrice and does not derive this "
            "parcel's price from areaInHa*pricePerHa*priceScale (FS25 Community "
            "LUADOC docs/script/Economy/Farmland.md, function load); this parser "
            "computes only the derived form, so this parcel's cost is unknown, "
            "not the derived figure")
        return None, scale, note

    if price_info is None or price_info["price_scale"] is None:
        scale = 1.0
        note = f"farmland id {fid}: no priceScale found in {pricing_name}, assumed 1.0"
    else:
        scale = price_info["price_scale"]
        note = None
    cost = round(area_ha * price_per_ha * scale, 2)
    return cost, scale, note


def compute_owned_totals(parcels, farm_id):
    """The owned parcel ids, their total hectares and their total value.

    ⛔ ALSO EXTRACTED FROM main() 2026-08-07, same reason. Returns a tuple so
    the three figures cannot drift apart: they are derived from one filter over
    one dict, and a test can pin the arithmetic rather than the fixture.

    ⛔ TECH-DEBT-103: total_value is None when ANY owned parcel's own cost is
    None (a declared fixed price -- see main()'s per-parcel loop). Summing the
    known costs and silently skipping the unknown one would UNDER-report the
    farm's land value while looking like a complete total -- the exact
    "confident wrong number" this sensor exists to refuse. Absence must
    propagate to the aggregate, not vanish into it."""
    owned_ids = sorted(fid for fid, p in parcels.items()
                       if p["owner_farm_id"] == farm_id)
    total_area_ha = round(sum(parcels[fid]["area_ha"] for fid in owned_ids), 4)
    owned_costs = [parcels[fid]["cost"] for fid in owned_ids]
    total_value = (None if any(c is None for c in owned_costs)
                   else round(sum(owned_costs), 2))
    return owned_ids, total_area_ha, total_value


### ------------------------------------------------------- field polygons --
# TECH-DEBT-095 (HIGH). The map's own map.i3d authors each field as a
# TransformGroup scene-graph node: a "fields" root, one child per field named
# "field<N>", each holding a point-container child whose own children are
# "point<N>" leaves carrying a translation relative to their parent. World
# position composes every ancestor's own translation, plus Y-axis rotation
# where an ancestor declares one, down to the point.
_FIELD_NAME_RE = re.compile(r"^field(\d+)$")
_POINT_NAME_RE = re.compile(r"^point\d+$")
_NOTE_AREA_RE = re.compile(r"field\d+&#xA;([\d.]+) ha")


def _tvec(attrib_value):
    """'x y z' -> (x, y, z) floats. Missing/empty -> (0.0, 0.0, 0.0), the i3d
    format's own default for an omitted translation/rotation attribute."""
    if not attrib_value:
        return (0.0, 0.0, 0.0)
    parts = attrib_value.split()
    if len(parts) != 3:
        raise ValueError(f"malformed i3d vector attribute {attrib_value!r}")
    return tuple(float(p) for p in parts)


def find_fields_block_text(i3d_text):
    """Isolate '<TransformGroup name="fields" ...>...</TransformGroup>' from
    a full i3d document's text, by depth-counting tags rather than a naive
    regex. The subtree nests TransformGroup/Shape/Note to arbitrary depth,
    and a non-greedy '.*?' up to the next two consecutive closing tags stops
    at the WRONG one on any field with more than two children -- measured:
    mapUS field54 has three (polygonPoints, then fieldMapIndicator, THEN its
    own close). Returns None if no 'fields' node exists."""
    idx = i3d_text.find('name="fields"')
    if idx == -1:
        return None
    start = i3d_text.rfind("<TransformGroup", 0, idx)
    if start == -1:
        return None
    tag_re = re.compile(r"<(/?)(TransformGroup|Shape|Note)\b[^>]*?(/?)>")
    depth = 0
    end = None
    for m in tag_re.finditer(i3d_text, start):
        closing, _tag, selfclose = m.groups()
        if selfclose:
            continue
        if closing:
            depth -= 1
            if depth == 0:
                end = m.end()
                break
        else:
            depth += 1
    return None if end is None else i3d_text[start:end]


def parse_field_polygons(i3d_text):
    """The map's field polygons -> ({field_id: entry}, fields_root_translation,
    fields_root_rotation, error_or_None).

    Each entry: field_translation/field_rotation (this field's OWN transform,
    relative to the fields root), container_translation/container_rotation
    (its point-container's transform), points (raw per-point translation
    tuples, relative to the container), authored_area_ha (the map's own
    <Note text="fieldN\\nN.NN ha"/> label, or None), and `unsupported`
    (a reason string, or None) for a field this parser refuses to position
    rather than approximate -- see compose_field_world_points.

    ⛔ NEVER MATCHES THE POINT-CONTAINER OR LABEL BY A FIXED NAME. mapUS
    field54 names its point container "fieldDimensions", not "polygonPoints"
    -- verified 2026-09-04 by running this parser against every field on
    every map this project has real files for and getting 76/77 (missing
    exactly field54) matching by NAME, 77/77 matching by STRUCTURE (a
    TransformGroup whose own children are point<N> leaves). The area label
    lives under "nameIndicator" on Montana/Lone Star/most of mapUS but under
    "fieldMapIndicator" on 64 of mapUS's 77 fields -- found the same way, by
    structure (any Note descendant of the field group) rather than by
    container name."""
    block = find_fields_block_text(i3d_text)
    if block is None:
        return None, None, None, 'no <TransformGroup name="fields"> node in this map\'s i3d'
    try:
        root = ET.fromstring(block)
    except ET.ParseError as e:
        return None, None, None, f"fields subtree of map.i3d did not parse as XML: {e}"

    try:
        root_translation = _tvec(root.attrib.get("translation"))
        root_rotation = _tvec(root.attrib.get("rotation"))
    except ValueError as e:
        return None, None, None, f"fields root: {e}"
    if root.attrib.get("scale"):
        return None, None, None, (
            "the fields root declares a scale= this parser does not support")

    fields = {}
    for fnode in root.findall("TransformGroup"):
        m = _FIELD_NAME_RE.match(fnode.attrib.get("name", ""))
        if not m:
            continue
        fid = int(m.group(1))
        unsupported = None
        try:
            field_translation = _tvec(fnode.attrib.get("translation"))
            field_rotation = _tvec(fnode.attrib.get("rotation"))
        except ValueError as e:
            return None, None, None, f"field{fid}: {e}"
        if field_rotation[0] != 0.0 or field_rotation[2] != 0.0:
            unsupported = (
                f"field{fid} declares a non-Y rotation {field_rotation} this "
                "parser does not compose")
        if fnode.attrib.get("scale"):
            unsupported = f"field{fid} declares a scale= this parser does not support"

        container = None
        for child in fnode.findall("TransformGroup"):
            if any(_POINT_NAME_RE.match(gc.attrib.get("name", ""))
                  for gc in child.findall("TransformGroup")):
                container = child
                break
        if container is None:
            continue  # a field group with no point polygon at all -- not this field's row to build

        try:
            container_translation = _tvec(container.attrib.get("translation"))
            container_rotation = _tvec(container.attrib.get("rotation"))
        except ValueError as e:
            return None, None, None, f"field{fid} polygon container: {e}"
        if unsupported is None:
            if container_rotation[0] != 0.0 or container_rotation[2] != 0.0:
                unsupported = (
                    f"field{fid}'s polygon container declares a non-Y rotation "
                    f"{container_rotation} this parser does not compose")
            elif container.attrib.get("scale"):
                unsupported = (
                    f"field{fid}'s polygon container declares a scale= this "
                    "parser does not support")

        points = []
        for pnode in container.findall("TransformGroup"):
            if not _POINT_NAME_RE.match(pnode.attrib.get("name", "")):
                continue
            try:
                points.append(_tvec(pnode.attrib.get("translation")))
            except ValueError as e:
                return None, None, None, f"field{fid} point: {e}"
        if len(points) < 3:
            continue  # not a real polygon; drop rather than fabricate one

        authored_area_ha = None
        for note in fnode.iter("Note"):
            nm = _NOTE_AREA_RE.search(note.attrib.get("text", ""))
            if nm:
                authored_area_ha = float(nm.group(1))
                break

        fields[fid] = {
            "field_translation": field_translation,
            "field_rotation": field_rotation,
            "container_translation": container_translation,
            "container_rotation": container_rotation,
            "points": points,
            "authored_area_ha": authored_area_ha,
            "unsupported": unsupported,
        }
    if not fields:
        return None, None, None, "map.i3d's 'fields' node has no field<N> polygon children"
    return fields, root_translation, root_rotation, None


def _rotate_y(x, z, degrees):
    """Rotate (x, z) by `degrees` about the Y (up) axis. The only rotation
    axis observed on a field or point-container node across all three maps
    this project has real files for: LoneStar field53 declares rotation="0
    0.360994 0" (X and Z exactly zero); every other field/container on all
    three maps declares no rotation at all. Untested sign convention for a
    genuinely mixed-axis rotation -- see parse_field_polygons's `unsupported`
    flag, which refuses to compose one rather than guess."""
    if degrees == 0.0:
        return x, z
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return x * cos_t + z * sin_t, -x * sin_t + z * cos_t


def compose_field_world_points(entry, fields_root_translation, fields_root_rotation):
    """A field polygon's points, transform-composed to world (x, z) pairs, or
    (None, reason) when this parser refuses to compose the transform.

    Regression-validated end to end (not merely unit-tested): with this
    composition, the polygon AREA CENTROID (polygon_area_centroid) of every
    field on savegame1/Montana (122/122) and savegame2/LoneStar (53/53)
    resolves, via world_to_raster_pixel + sample_farmland_id, to the SAME
    farmland id the retired field_id==farmland_id assumption claimed -- see
    test_td095_field_farmland_resolver.py."""
    if entry.get("unsupported"):
        return None, entry["unsupported"]
    root_rx, _root_ry, root_rz = fields_root_rotation
    if root_rx != 0.0 or root_rz != 0.0:
        return None, (
            f"fields root declares a non-Y rotation {fields_root_rotation} "
            "this parser does not compose")
    ftx, _fty, ftz = entry["field_translation"]
    fry = entry["field_rotation"][1]
    ctx, _cty, ctz = entry["container_translation"]
    croty = entry["container_rotation"][1]
    root_tx, _root_ty, root_tz = fields_root_translation
    root_ry = fields_root_rotation[1]

    world_points = []
    for (px, _py, pz) in entry["points"]:
        x, z = _rotate_y(px, pz, croty)
        x += ctx
        z += ctz
        x, z = _rotate_y(x, z, fry)
        x += ftx
        z += ftz
        x, z = _rotate_y(x, z, root_ry)
        x += root_tx
        z += root_tz
        world_points.append((x, z))
    return world_points, None


def polygon_area_centroid(points):
    """(cx, cz), signed_area_m2 -- the polygon's AREA centroid (shoelace-
    weighted), never the plain average of its vertices.

    ⛔ THE VERTEX AVERAGE IS WRONG, AND MEASURED WRONG. On Montana field 65
    (297 vertices, unevenly spaced -- hundreds of points along one long
    curved edge, few on the straight ones) the vertex average resolved to a
    DIFFERENT farmland parcel than the polygon itself, breaking the 122/122
    regression by exactly one field; the area centroid does not (verified
    122/122). A dense, curved edge pulls a plain average toward itself; the
    area centroid is invariant to how densely a boundary happens to be
    authored."""
    n = len(points)
    signed_area = 0.0
    cx = 0.0
    cz = 0.0
    for i in range(n):
        x1, z1 = points[i]
        x2, z2 = points[(i + 1) % n]
        cross = x1 * z2 - x2 * z1
        signed_area += cross
        cx += (x1 + x2) * cross
        cz += (z1 + z2) * cross
    signed_area *= 0.5
    if abs(signed_area) < 1e-9:
        # Degenerate (zero-area / collinear) polygon -- fall back to the
        # vertex average rather than divide by ~zero. Not the normal path.
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n), signed_area
    return (cx / (6 * signed_area), cz / (6 * signed_area)), signed_area


def shoelace_area_ha(points):
    """The polygon's own area (item 3), in hectares -- the same shoelace sum
    polygon_area_centroid computes, kept as its own function per this file's
    established convention (pixels_to_hectares, compute_parcel_cost) of
    extracting anything that feeds a headline number so it can be tested and
    mutated on its own."""
    n = len(points)
    total = 0.0
    for i in range(n):
        x1, z1 = points[i]
        x2, z2 = points[(i + 1) % n]
        total += x1 * z2 - x2 * z1
    return abs(total) / 2.0 / M2_PER_HECTARE


def world_to_raster_pixel(world_x, world_z, map_width_m, map_height_m,
                          raster_width, raster_height):
    """World (x, z) -> raster (px, pz), or None if outside the raster. See
    CITE_WORLD_TO_RASTER for the engine formula this applies verbatim."""
    px = math.floor(raster_width * (world_x + map_width_m / 2.0) / map_width_m)
    pz = math.floor(raster_height * (world_z + map_height_m / 2.0) / map_height_m)
    if not (0 <= px < raster_width and 0 <= pz < raster_height):
        return None
    return px, pz


def sample_farmland_id(pixels, raster_width, pixel):
    """Row-major sample of the decoded GRLE raster: pixels[pz*width + px].

    Row-major, x-fast, validated (not assumed) against the 175 fields across
    savegame1/Montana and savegame2/LoneStar whose farmland id is
    independently known from the retired field_id==farmland_id result: all
    175/175 resolve to that same id through this indexing. Column-major and
    both single-axis flips were tried and rejected -- 0/175 each."""
    px, pz = pixel
    return pixels[pz * raster_width + px]


def resolve_spatial_field_farmland(field_polygons, fields_root_translation,
                                   fields_root_rotation, pixels, raster_width,
                                   raster_height, map_width_m, map_height_m):
    """{field_id: result} for every field the MAP knows about (not the save --
    see build_spatial_field_rows for the save-side join). result is:
        {"farmland_id": int or None, "area_ha": float or None,
         "authored_area_ha": float or None, "straddles_farmland": bool or None,
         "reason": str or None}
    `reason` is set (and farmland_id/area_ha/straddles_farmland are None)
    exactly when the field could not be resolved -- never a guess, never a
    silently dropped field."""
    results = {}
    for fid, entry in field_polygons.items():
        authored = entry.get("authored_area_ha")
        world_points, reason = compose_field_world_points(
            entry, fields_root_translation, fields_root_rotation)
        if world_points is None:
            results[fid] = {"farmland_id": None, "area_ha": None,
                            "authored_area_ha": authored,
                            "straddles_farmland": None, "reason": reason}
            continue
        (cx, cz), _signed_area = polygon_area_centroid(world_points)
        pixel = world_to_raster_pixel(cx, cz, map_width_m, map_height_m,
                                      raster_width, raster_height)
        if pixel is None:
            results[fid] = {"farmland_id": None, "area_ha": None,
                            "authored_area_ha": authored,
                            "straddles_farmland": None,
                            "reason": "field polygon's area centroid falls "
                                     "outside this map's raster bounds"}
            continue
        farmland_id = sample_farmland_id(pixels, raster_width, pixel)
        # Straddle check: sample every VERTEX, not only the centroid. A field
        # whose vertices land on more than one distinct farmland id crosses a
        # parcel boundary; the centroid answer is still reported (the best
        # single answer this parser has), but the crossing becomes visible
        # instead of silently absorbed into one id.
        vertex_ids = set()
        for (vx, vz) in world_points:
            vpixel = world_to_raster_pixel(vx, vz, map_width_m, map_height_m,
                                           raster_width, raster_height)
            if vpixel is not None:
                vertex_ids.add(sample_farmland_id(pixels, raster_width, vpixel))
        results[fid] = {
            "farmland_id": farmland_id,
            "area_ha": round(shoelace_area_ha(world_points), 4),
            "authored_area_ha": authored,
            "straddles_farmland": len(vertex_ids - {None}) > 1,
            "reason": None,
        }
    return results


def build_spatial_field_rows(field_ids, spatial_results, parcels, farm_id,
                             calibration_notes):
    """One ownership row per SAVE-side field id, via the spatial join.
    `spatial_results` is keyed by the MAP's own field ids (resolve_spatial_
    field_farmland, run over the map's polygons); a save-side field id absent
    from it has no map-side polygon at all and reports null with a reason,
    appended to calibration_notes exactly like the retired identity join's
    unmatched branch did.

    Appends to `calibration_notes` in place, for the unresolved and
    straddling branches."""
    rows = []
    for field_id in field_ids:
        r = spatial_results.get(field_id)
        if r is None:
            calibration_notes.append(
                f"field id {field_id} has no matching polygon in this map's "
                "i3d -- reported with farmland_id=null rather than guessed")
            rows.append({"field_id": field_id, "farmland_id": None,
                        "identity_basis": None, "owned": None,
                        "owner_farm_id": None, "area_ha": None,
                        "authored_area_ha": None, "straddles_farmland": None})
            continue
        if r["farmland_id"] is None:
            calibration_notes.append(f"field id {field_id}: {r['reason']}")
            rows.append({"field_id": field_id, "farmland_id": None,
                        "identity_basis": None, "owned": None,
                        "owner_farm_id": None, "area_ha": None,
                        "authored_area_ha": r["authored_area_ha"],
                        "straddles_farmland": None})
            continue
        parcel = parcels.get(r["farmland_id"])
        owner_farm_id = parcel["owner_farm_id"] if parcel else None
        if r["straddles_farmland"]:
            calibration_notes.append(
                f"field id {field_id}: polygon vertices resolve to more than "
                "one farmland id -- the field straddles a parcel boundary; "
                f"farmland_id {r['farmland_id']} is this field's centroid "
                "parcel, not a full-coverage answer")
        rows.append({
            "field_id": field_id,
            "farmland_id": r["farmland_id"],
            "identity_basis": SPATIAL_JOIN_BASIS,
            "owned": (owner_farm_id == farm_id) if parcel else None,
            "owner_farm_id": owner_farm_id,
            "area_ha": r["area_ha"],
            "authored_area_ha": r["authored_area_ha"],
            "straddles_farmland": r["straddles_farmland"],
        })
    return rows


def build_field_coverage(map_field_ids, save_field_ids):
    """TECH-DEBT-095's required output: the coverage between the map's own
    field polygons and the save's own field ids. Not a falsifiability check
    on an assumption -- there is no assumption left to falsify -- a MEASURED
    count of which side has data the other lacks.

    Either side being None (map i3d unreadable / save fields.xml unreadable)
    still reports rather than crashing."""
    if map_field_ids is None or save_field_ids is None:
        return {
            "checked": False,
            "reason": ("map field polygons unavailable" if map_field_ids is None
                      else "save fields.xml unavailable"),
        }
    map_ids = set(map_field_ids)
    save_ids = set(save_field_ids)
    map_only = sorted(map_ids - save_ids)
    save_only = sorted(save_ids - map_ids)
    overlap = sorted(map_ids & save_ids)
    return {
        "checked": True,
        "map_field_id_count": len(map_ids),
        "save_field_id_count": len(save_ids),
        "overlap_count": len(overlap),
        "map_only_count": len(map_only),
        "save_only_count": len(save_only),
        "map_only_field_ids": map_only,
        "save_only_field_ids": save_only,
        "note": (
            "save_only field ids have no map-side polygon and resolve to "
            "farmland_id=null with a reason -- see field_ownership.data. "
            "map_only field ids are on the map but the save has no matching "
            "<field>; they never appear as a row here."
        ),
    }


def build_shoelace_label_check(field_results):
    """Item 3's self-check: this parser's own shoelace area against the map's
    own authored <Note text="fieldN\\nN.NN ha"/> label, for every field that
    carries one. Corroboration, not a blocking gate -- a map author is free
    to omit the label (none of the three maps this project has do), so its
    absence must not fail the run. Reported so a wrong shoelace computation
    is VISIBLE rather than silently trusted."""
    checked = 0
    mismatches = []
    for fid, r in field_results.items():
        if r["authored_area_ha"] is None or r["area_ha"] is None:
            continue
        checked += 1
        diff = round(abs(r["area_ha"] - r["authored_area_ha"]), 4)
        # The label is authored to 2 decimals; a hair looser than the 0.005ha
        # of pure rounding noise on both sides, tight enough to still catch a
        # genuinely wrong area (an axis swap, a missed point).
        if diff > 0.02:
            mismatches.append({"field_id": fid, "computed_area_ha": r["area_ha"],
                              "authored_area_ha": r["authored_area_ha"],
                              "diff_ha": diff})
    return {
        "checked": checked,
        "mismatches": mismatches,
        "agrees": checked > 0 and not mismatches,
    }


def file_provenance(path):
    """sec. 2.1 source record. Hashes each source file WHOLE.

    ⚠ This docstring used to claim it "hashes only what this domain actually
    reads". That is false for `mod_zip_path`: the domain reads two entries
    inside the archive and this hashes every byte of it. The behaviour is more
    conservative than the old wording claimed, not less -- an unrelated change
    inside the zip moves the hash -- so this is a documentation-accuracy fix,
    and the extra sensitivity is deliberate rather than a bug to file."""
    stat = os.stat(path)
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return {"path": path, "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size, "sha256": digest}


def source_set_hash(sources):
    """sec. 2.1: sha256 over the sorted `path\\0sha256` lines. This script
    carries its own copy rather than importing a sibling's, as read_fleet.py
    and read_weather.py each do, so it owes its own mutation proof."""
    lines = sorted("%s\0%s" % (s["path"], s["sha256"]) for s in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def roll_up(sections):
    """Top-level status/reason -- sec. 6.3.3. TOTAL, ORDERED, FIRST MATCH WINS.

        0.5 the section set is EMPTY        -> a defect, never a status
        1.  ANY section unavailable/partial -> "partial"
        2.  EVERY section unknown_by_design -> "unknown_by_design"
        3.  otherwise (>=1 ok, none failed) -> "ok"

    Rule 0.5 exists because rule 2 is VACUOUSLY TRUE over an empty set:
    all([]) is True in every language a builder will use, so a script that
    emitted no sections would report "no data of any kind on this farm" -- a
    positive claim about the farm derived from having produced nothing.

    ⚠ SWAPPING RULES 1 AND 2 IS A NO-OP AND NO TEST CAN CATCH IT. The
    conditions are disjoint: rule 2 requires every section unknown_by_design,
    which means none is unavailable or partial, which is rule 1 failing. The
    observable mutation is widening rule 2 from EVERY to ANY and placing it
    first; that is the misreading a builder actually makes, and the land suite
    mutates exactly that rather than the unobservable reorder."""
    if not sections:
        raise ValueError(
            "sec. 6.3.3 rule 0.5: the section set is empty. Every registered "
            "domain emits every section every time, so this is a defect in this "
            "script, not a status about the farm.")
    failed = sorted(n for n, s in sections.items()
                    if s["status"] in ("unavailable", "partial"))
    if failed:
        return "partial", "; ".join(
            f"{n}: {sections[n]['reason']}" for n in failed)
    if all(s["status"] == "unknown_by_design" for s in sections.values()):
        return "unknown_by_design", "no data of any kind on this farm for this domain"
    return "ok", None


def _section(status, reason, shape, capability_ids, typing, typing_guarantee,
             identity_fields, empty_means, absence_guarantee,
             interpretation_guarantee, source_elements, blocked_by, count, data):
    """The sec. 6.2 section, built through ONE constructor so every section in
    this domain carries the same closed key set.

    ⚠ FOURTEEN KEYS, NOT THIRTEEN. The four merged sibling domains
    (livestock, fleet, farm_ledger, weather) emit thirteen -- they were built
    against rev 4, before `interpretation_guarantee` existed. Spec rev 6
    sec. 6.2 makes the enumeration exhaustive and REQUIRED, and this domain
    follows the spec rather than the siblings: the field->farmland join is a
    reading no schema compels, which is precisely the case rev 5 added the
    field for. Without it the ruling would have to live in `reason` prose --
    a decision nobody can enumerate, which is the exact defect sec. 6.2
    diagnoses. The siblings being at thirteen is a drift finding against them,
    not a licence for a fifth divergent envelope.

    A missing key is a build failure, never a default (sec. 6.2): defaulting is
    how a guard gets silently skipped, and tooth 1 can only detect an
    undeclared read of a blocked element if declaration is universal."""
    if not source_elements:
        # sec. 6.2: "source_elements is never empty" -- a section that read
        # nothing has nothing to report and is a defect. Absence must fail.
        raise ValueError(f"section built with empty source_elements: {shape}")
    return {
        "status": status,
        "reason": reason,
        "shape": shape,
        "capability_ids": list(capability_ids),
        "typing": typing,
        "typing_guarantee": typing_guarantee,
        "identity_fields": identity_fields,
        "empty_means": empty_means,
        "absence_guarantee": absence_guarantee,
        "interpretation_guarantee": interpretation_guarantee,
        "source_elements": source_elements,
        "blocked_by": blocked_by,
        "count": count,
        "data": data,
    }


# Element-level source locators, NOT file-level -- sec. 6.2. The distinction is
# load-bearing here: this domain reads farms.xml, and a file-level declaration
# ("farms.xml:*") would intersect the registry's blocked
# farms.xml:farm/finances/stats/fieldPurchase and fire tooth 1 against a read
# that has nothing to do with it. What this domain actually reads from that
# file is the authoritative farm list, farm/@farmId, which does not intersect.
# Declare what you read, at the depth you read it.
ELEM_FARM_LIST = "farms.xml:farm@farmId"
ELEM_FARMLAND_OWNER = "farmland.xml:farmlands/farmland@farmId"
ELEM_FARMLAND_ID = "farmland.xml:farmlands/farmland@id"
ELEM_FIELD_ID = "fields.xml:fields/field@id"
ELEM_MAP_ID = "careerSavegame.xml:careerSavegame/settings/mapId"
ELEM_PRICE_PER_HA = "config/farmlands.xml:farmlands@pricePerHa"
ELEM_PRICE_SCALE = "config/farmlands.xml:farmlands/farmland@priceScale"
ELEM_RASTER = "infoLayer_farmlands.grle:*"
ELEM_MAP_DIMS = "map.xml:map@width"
ELEM_MAP_I3D_FIELDS = "map.i3d:fields/field<N>/*/point<N>@translation"
# environment.xml is opened EVERY run by parse_current_day(), regardless of
# CROSS_CHECK_ENABLED, and was previously declared nowhere -- absent from every
# section's source_elements, from provenance.sources and from source_set_hash.
# That breaks this file's own "declare what you read" principle, and tooth 1
# can only detect an undeclared read of a blocked element if declaration is
# universal. Declared at the depth it is read: the single <currentDay> element.
ELEM_CURRENT_DAY = "environment.xml:environment/currentDay"


# --- sec. 6.5 rule 2: typing_guarantee is a citation FOR A COERCION ----------
#
# ⛔ AND A CITATION FOR A NON-COERCION IS NOT ALLOWED. read_fleet.py:126 states
# the rule this domain got wrong by shipping `{}` everywhere: "a citation for a
# non-coercion would be a claim about a guarantee that is not being used." Most
# figures this domain reports are COMPUTED -- decoded from a raster, then
# multiplied -- so no schema governs them and there is nothing to cite. They
# carry an explicit non-schema note instead, per the owner's ruling 2026-08-07:
# silence is indistinguishable from "never written", which is the defect being
# closed here. That is DEC-001 applied to a trust note rather than to a parser.
#
# ⛔ PER FIELD, NEVER BLANKET -- read_productions.py:141: "a blanket citation
# cannot be checked against the attribute it claims to cover."
#
# ⚠ THE TRAP, recorded because the next reader will meet it: `farmlands.xsd:150`
# DOES declare an `areaInHa` attribute. This script never reads it -- area is
# decoded from the raster -- so citing it for `area_ha` would be an invented
# citation for a value that does not come from that file.
#
# Verified 2026-08-07 by OPENING both files under <install>/shared/xml/schema/
# (88 XSDs). Size + digest travel with the line number, because a line number
# alone goes stale silently:
#   farmlands.xsd        13470 bytes  sha256 f89fdf7c5433aa0124e7fa6c...
#   fields_savegame.xsd  25963 bytes  sha256 f770a3d7795859630e35e64a...
_G_FLOAT_FARMLANDS = "g_float -> xs:restriction base=xs:float (farmlands.xsd:30-33)"
_G_INT_FIELDS_SG = "g_int -> xs:restriction base=xs:integer (fields_savegame.xsd:50-52)"

CITE_PRICE_PER_HA = (
    "farmlands.xsd:189 declares farmlands@pricePerHa as " + _G_FLOAT_FARMLANDS)
# ⚠ COVERS THE COERCION AND *ONE OF THREE* FALLBACK CAUSES, and the difference
# ships. The 1.0 substitution fires at the `price_info is None or
# price_info["price_scale"] is None` test in main(); an XSD `default`
# materialises for an ABSENT ATTRIBUTE ON A PRESENT ELEMENT, so it reaches
# exactly one of the three ways that test can be true:
#   (a) element present, @priceScale absent      -> default="1" DOES license it
#       (parse_pricing_xml's `.get("priceScale")` -> None)
#   (b) no <farmland> element carries this id, or   -> nothing to default ON
#       <farmlands> itself is absent (`find` -> None, returns an empty dict)
#   (c) element present but @id absent/non-integer  -> the attribute is not
#       and the row was dropped at the `except         absent; it is present
#       (KeyError, ValueError): continue`              and ignored
# ⛔ This string has now been wrong in BOTH directions, which is why it names
# which is which: it shipped "no schema licenses" unconditionally (false in
# (a), the common case -- S2), and the first correction then said "the
# schema's own declared default" unconditionally (false in (b) and (c) -- F-A).
CITE_PRICE_SCALE = (
    "farmlands.xsd:171 declares farmlands/farmland@priceScale as "
    + _G_FLOAT_FARMLANDS
    + '. The same line declares default="1", which covers the coerced value '
      "and ONE of the three ways a 1.0 is substituted here: where the "
      "<farmland> element for this id is present and only @priceScale is "
      "absent, the substituted 1.0 IS the schema's declared default. It does "
      "not cover the other two -- no <farmland> element carrying this id, or "
      "an element dropped because its @id is absent or non-integer -- because "
      "an XSD default supplies an absent attribute on a PRESENT element and "
      "attaches to neither. In those two the 1.0 is this script's assumption "
      "and no schema licenses it. All three raise a calibration note, and the "
      "note does not record which one applied.")
CITE_FIELD_ID = (
    "fields_savegame.xsd:156 declares fields/field@id as " + _G_INT_FIELDS_SG
    + ', use="required"')

_COMPUTED = ("COMPUTED, NOT COERCED -- no schema governs this value, and this "
             "note is deliberately NOT a citation. ")
GUARANTEE_METERS_PER_PIXEL = _COMPUTED + (
    "Derived as the map's declared width (map.xml:map@width) divided by the "
    "decoded raster width.")
GUARANTEE_AREA_HA = _COMPUTED + (
    "Derived as decoded pixel_count * meters_per_pixel^2 / 10000 "
    "(pixels_to_hectares).")
GUARANTEE_COST = _COMPUTED + "Derived as area_ha * price_per_ha * price_scale."
GUARANTEE_TOTAL_AREA_HA = _COMPUTED + (
    "Derived as the sum of area_ha over the parcels this farm owns.")
GUARANTEE_LAND_VALUE = _COMPUTED + (
    "Derived as the sum of cost over the parcels this farm owns.")
GUARANTEE_FARMLAND_ID = (
    "DERIVED, NOT COERCED -- the spatial join's output (a raster sample at "
    "the field polygon's own area centroid), not a value read from any "
    "file. The join is licensed in interpretation_guarantee (ARCH-R3-06) "
    "and never here.")
GUARANTEE_OWNED = (
    "DERIVED, NOT COERCED -- the boolean result of comparing this parcel's "
    "owner_farm_id against the queried farm_id.")
GUARANTEE_FIELD_AREA_HA = _COMPUTED + (
    "Derived via the shoelace formula (shoelace_area_ha) over the field "
    "polygon's world-composed vertices (map.i3d).")
GUARANTEE_STRADDLES_FARMLAND = (
    "DERIVED, NOT COERCED -- true when the field polygon's own vertices "
    "sample more than one distinct farmland id (resolve_spatial_field_"
    "farmland's straddle check), false when they agree, null when the "
    "field itself could not be resolved.")
GUARANTEE_AUTHORED_AREA_HA = (
    "READ, NOT COERCED -- the map author's own printed <Note text=\"fieldN"
    "\\nN.NN ha\"/> label (map.i3d), parsed as a float. No schema governs "
    "this optional developer annotation; null where a field carries none.")

# ⚖ ARCH-R3-05 -- the owner 2026-08-07b, spec § 6.5 rev 10, carried under DEC-077.
#
# "In the savegame's farmland.xml, farmlands/farmland@id and
# farmlands/farmland@farmId may be coerced to int, anywhere in the file, by any
# domain." FILE-WIDE, so it is NOT map-scoped: unlike ARCH-R3-04 it is present
# on every save, which is why it is appended outside the on_ruled_map branch.
#
# ⛔ `kind` is design_ruling PERMANENTLY and may NEVER be relabelled
# `schema_cited`. What is missing is a SCHEMA, not an observation: 12 savegame
# schemas exist and none governs farmland; farmlands.xsd governs a different
# file (its root is <map>, this file's root is <farmlands>) and declares no
# @farmId at all. A census of conforming ids is INDUCTION, never a citation.
#
# ⛔ AND IT GETS NO `confirmed_by` FIELD, EVER. Spec § 6.5: permanently
# un-retirable -- not "outstanding", not "awaiting a test". The three earlier
# rulings were missing an OBSERVATION, which can be taken; this one is missing a
# published schema, which is GIANTS's to publish and not ours to obtain.
def build_arch_r3_05(raw_id_conformance):
    """One entry per ruling, never split, never merged (§ 6.2.1 rule 3)."""
    return {
        "kind": "design_ruling",
        "ruling": "ARCH-R3-05",
        "scope": "savegame farmland.xml, file-wide: farmlands/farmland@id and @farmId",
        # DERIVED per save, never hardcoded (DEC-074 ②). None where the file
        # could not be read -- the spec forbids a default `false` here.
        "falsifiable_on_this_save": (
            raw_id_conformance.get("falsifiable_on_this_save")
            if raw_id_conformance else None),
        "falsifier": raw_id_conformance,
        "text": (
            "farmlands/farmland@id and @farmId in the SAVEGAME farmland.xml are "
            "coerced to int. No schema governs that file, so this is a DECISION, "
            "not a measurement. It licenses the coercion ONLY: it says nothing "
            "about what the ids MEAN -- not that @farmId joins to farms.xml, not "
            "that @farmId=0 means unowned, and not that a parcel id relates to a "
            "field id (that reading is ARCH-R3-06's, on its own evidence). It is "
            "not a licence to aggregate, and it does not license the silent "
            "`except (KeyError, ValueError): continue` that drops a malformed row."
        ),
    }


# ⚖ ARCH-R3-06, TECH-DEBT-095 (HIGH), 2026-09-04. Replaces ARCH-R3-04, which
# licensed `field_id == farmland_id` -- permanently unfalsifiable, scoped to
# one map. That assumption was measured FALSE on MapUS/savegame3 (map/save
# field-id overlap 64/77; see build_field_coverage). ARCH-R3-06 is not
# scoped to one map: it is the METHOD every map now uses.
#
# ⚠ ITS AREA CLAIM IS FALSIFIABLE PER SAVE. ITS JOIN CLAIM IS NOT
# (TECH-DEBT-107). This comment previously made the per-save claim unqualified
# and cited both carried measurements as its evidence -- including
# build_field_coverage, whose OWN docstring disclaims being one ("Not a
# falsifiability check on an assumption ... a MEASURED count"). A shoelace
# MISMATCH does refute the join, because the sample is taken at the polygon's
# area centroid; shoelace AGREEMENT refutes nothing about position, because the
# sum is invariant under rotation and translation. The join's position rests on
# a build-time cross-map regression instead. See build_arch_r3_06's `text`.
def build_arch_r3_06(field_coverage, shoelace_check):
    """One entry per ruling, never split, never merged (§ 6.2.1 rule 3)."""
    return {
        "kind": "design_ruling",
        "ruling": "ARCH-R3-06",
        # DERIVED FROM THE DATA, copying build_raw_id_conformance (ARCH-R3-05,
        # :679) rather than inventing a second shape: TRUE EXACTLY WHERE THE
        # CHECK FOUND A CONTRADICTION, never merely where it was able to look.
        # None where nothing was measured -- the spec forbids a default `false`.
        # ⚠ TECH-DEBT-107. This shipped as `bool(checked)`, which is "we were
        # able to look" -- the exact shape the comment at :676 names as wrong.
        # A shoelace MISMATCH does falsify this ruling: the join samples the
        # polygon's AREA CENTROID, so a polygon whose area is provably wrong
        # has a provably wrong centroid and lands in the wrong parcel.
        # Shoelace AGREEMENT corroborates nothing about the join -- see `text`.
        "falsifiable_on_this_save": (
            bool(shoelace_check.get("mismatches"))
            if shoelace_check and shoelace_check.get("checked") else None),
        "text": (
            "Field ownership is attributed by sampling infoLayer_farmlands.grle "
            "at the AREA CENTROID of the field's own polygon (map.i3d), after "
            "transforming world -> raster via the engine's own "
            "FarmlandManager:convertWorldToLocalPosition formula (see "
            "CITE_WORLD_TO_RASTER / typing_guarantee.farmland_id). This "
            "replaces ARCH-R3-04's field_id == farmland_id identity "
            "assumption, retired 2026-09-04 after a HIGH-severity finding "
            "demonstrated it false on MapUS/savegame3. Unlike ARCH-R3-04 "
            "this is a MEASURED join, not a permanently unfalsifiable design "
            "decision. TWO CLAIMS LIVE HERE AND THEY CARRY DIFFERENT "
            "EVIDENCE, so do not read one as the other. "
            "(1) The AREA is corroborated per save: shoelace_label_check "
            "compares this parser's own polygon-area formula against the map "
            "author's own printed ha label, and a mismatch is a genuine "
            "refutation -- a polygon whose area is wrong has a wrong area "
            "centroid, so the sample lands in the wrong parcel. "
            "(2) The JOIN'S POSITION is NOT corroborated per save, and no "
            "measurement carried in this object can corroborate it. The "
            "shoelace sum is INVARIANT UNDER ROTATION AND TRANSLATION -- "
            "precisely the two degrees of freedom the world-space transform "
            "consists of -- so shoelace AGREEMENT is silent about where the "
            "polygon sits. field_coverage compares field-id SETS and never "
            "geometry; it documents itself as a measured count, not a "
            "falsifier. The join's position rests instead on a BUILD-TIME "
            "CROSS-MAP REGRESSION against the retired identity result "
            "(Montana 122/122, LoneStar 53/53), which is evidence but is NOT "
            "a per-save falsifier: `checked: N` means N fields had an area "
            "label to compare, never that N fields had their POSITION "
            "corroborated. A "
            "single centroid sample cannot see a field that genuinely "
            "straddles two farmland parcels; straddles_farmland flags "
            "exactly that case on the affected rows rather than silently "
            "picking a side."
        ),
        "field_coverage": field_coverage,
        "shoelace_label_check": shoelace_check,
    }


# ⛔ DELIBERATELY ABSENT, AND IT STAYS ABSENT: `owner_farm_id`.
# It is coerced from the SAVEGAME farmland.xml in
# parse_savegame_farmland_ownership, which no schema governs, so there is
# nothing to cite. `typing_guarantee` is CITATIONS ONLY (§ 6.5 rule 2) and the
# licence for that coercion lives in `interpretation_guarantee` as ARCH-R3-05.
# Putting the ruling's prose here instead would be the § 6.5 mutation "move the
# ruling's prose into typing_guarantee -> red". Absent here is the correct
# shape, not an unfinished one.


def build_sections(map_record, parcels, owned_ids, owned_total_area_ha,
                   owned_land_value, fields_out, field_err, field_coverage,
                   calibration_notes=None, raw_id_conformance=None,
                   shoelace_check=None):
    """The four sec. 6.2 sections this domain emits, every run.

    `calibration_notes` is the SAME list main() later hands to
    build_legacy_top_level, which derives `calibration_needed` from its
    length -- so appending here is how a per-field resolution failure reaches
    that flag. Defaulted for fixtures that do not care; never skipped, only
    discarded.

    `raw_id_conformance` carries ARCH-R3-05's per-save falsifier. Defaulted so
    existing fixtures keep working; where it is None the ruling still ships and
    reports `falsifiable_on_this_save: null`, which is the spec's required value
    for a measurement not taken -- never `false`.

    `field_coverage` (build_field_coverage) and `shoelace_check`
    (build_shoelace_label_check) are the two measurements ARCH-R3-06 carries.
    ⚠ THEY CORROBORATE THE AREA, NOT THE JOIN'S POSITION (TECH-DEBT-107); this
    paragraph previously attributed per-save corroboration to the spatial join
    itself, which is the claim the ruling no longer makes -- and
    build_field_coverage disclaims being a falsifier in its own docstring. See
    build_arch_r3_06's `text` for what each can and cannot refute. Both default to
    None for fixtures that do not care; a None `shoelace_check` reports
    `falsifiable_on_this_save: null` on the ruling -- the spec's required
    value for a measurement not taken, never `false`, exactly as ARCH-R3-05
    does two paragraphs up. ⚠ This docstring claimed `false` until
    TECH-DEBT-107; that contradicted the paragraph above it AND the shipped
    behaviour it described was itself the defect."""
    if calibration_notes is None:
        calibration_notes = []
    raster_elements = [ELEM_RASTER, ELEM_PRICE_PER_HA, ELEM_PRICE_SCALE,
                       ELEM_FARMLAND_ID, ELEM_FARMLAND_OWNER]

    # The area math is the engine's own, and this is a citation rather than
    # an argument: FarmlandManager:loadFarmlandData computes
    # transformFactor = terrainSize / localMapWidth, pixelToSqm =
    # transformFactor^2, ha = areaToHa(pixelCount, pixelToSqm) -- one factor
    # for BOTH axes, which is why gate 2 refuses non-square pixels rather than
    # averaging them.
    # ⚖ OWNER RULING, the owner, 2026-08-07: NO DESIGN RULING IS INTENDED HERE, so
    # this section stops declaring one. It shipped `kind: "design_ruling"` with
    # `ruling: None` -- a middle state sec. 6.5 does not define. The spec gives
    # exactly two shapes (`null`, or an object whose `kind` is `schema_cited` or
    # `design_ruling`), rule 2 makes a `design_ruling` naming no ruling a build
    # failure, and rule 3 gives the only other exit: "the section reports what
    # it observed without the interpretation." Minting a ruling to fill the hole
    # was explicitly refused -- that is the owner's call, not a script's.
    #
    # ⚠ WHAT WENT WITH IT, recorded rather than silently dropped. The block
    # carried two pieces of prose, both preserved here and both still true:
    #   `text` -- parcel area is derived from a decode of the map's
    #     infoLayer_farmlands.grle raster, not read from a declared field. The
    #     decode is gate-checked every run (gate 1: decoded id set equals
    #     farmland.xml's; gate 2: pixel count matches the header and pixels are
    #     square against the map's declared size), and the script refuses to
    #     emit any area or value figure when either gate fails.
    #   `engine_support` -- FS25 Community LUADOC @86f08357778f
    #     docs/script/Economy/FarmlandManager.md: getFarmlandIdAtWorldPosition
    #     reads the same info-layer via getBitVectorMapPoint, and
    #     loadFarmlandData derives area as pixelCount*(terrainSize/
    #     localMapWidth)^2. This CORROBORATES the method and was deliberately
    #     held NON-LICENSING: engine parity is not a schema guarantee about this
    #     map's file.
    # That second point is the whole reason the ruling was never sought: a
    # corroboration held non-licensing is, by its own terms, not a licence. The
    # gates it describes are enforced in code and tested; none of that moved.
    # ⛔ The retired `ruling: None  # TODO ARCH-R3-04` cross-reference does NOT
    # come back with any future object here. ARCH-R3-06 (ARCH-R3-04's
    # successor) licenses the SPATIAL JOIN (spec sec. 6.5), not the raster
    # area derivation, so filling it in would never have licensed this block
    # and a reader resolving the ruling would have believed otherwise.
    # ⚖ DEC-077 / § 6.2.1: this field is now a LIST. ONE form only -- `[]` when
    # there is no ruled reading, never `null`; a one-element list when there is
    # one, never a bare object. Uniformly iterable, so no consumer branches on
    # type and one that forgets the empty case iterates zero times.
    #
    # ⛔ THE RASTER READING ITSELF IS STILL UNLICENSED, and that has not changed:
    # everything the retired block said above still holds, and `[]` is how a
    # section says "no ruled reading here". What DID change is that the sections
    # declaring ELEM_FARMLAND_ID / ELEM_FARMLAND_OWNER coerce those ids, and that
    # coercion is licensed by ARCH-R3-05.
    #
    # ⚠ SO `[]` IS NOT UNIFORM ACROSS THE FOUR SECTIONS, and the split is by what
    # each section actually READS -- the "declare what you read" principle this
    # file already applies to source_elements:
    #   map_calibration  -> []          (declares neither farmland.xml element)
    #   farmland_parcels -> [-05]       (emits owner_farm_id, coerced)
    #   owned_land       -> [-05]       (its owned set is selected on that value)
    #   field_ownership  -> [-04, -05] on the ruled map, [-05] off it
    # A section that emits a value coerced under a ruling and declares `[]` would
    # tell a reader auditing ruled readings that there are none, which is false.
    raster_interpretation = []
    arch_r3_05 = build_arch_r3_05(raw_id_conformance)

    map_section = _section(
        status="ok", reason=None, shape="record",
        capability_ids=CAPABILITY_IDS,
        typing={"meters_per_pixel": "float", "price_per_ha": "float"},
        typing_guarantee={
            "meters_per_pixel": GUARANTEE_METERS_PER_PIXEL,
            "price_per_ha": CITE_PRICE_PER_HA,
        },
        identity_fields=["map_id"],
        empty_means=None,
        absence_guarantee=None,
        interpretation_guarantee=raster_interpretation,
        source_elements=[ELEM_MAP_ID, ELEM_MAP_DIMS, ELEM_RASTER, ELEM_PRICE_PER_HA],
        blocked_by=None,
        count=1,
        data=map_record,
    )

    parcels_section = _section(
        status="ok", reason=None, shape="keyed_records",
        capability_ids=CAPABILITY_IDS,
        typing={"area_ha": "float", "price_scale": "float", "cost": "float",
                "owner_farm_id": "int"},
        # `owner_farm_id` is absent on purpose -- see the ARCH-R3-05 hold note
        # beside the constants above. It is the one field here that needs a
        # ruling rather than a citation.
        typing_guarantee={
            "area_ha": GUARANTEE_AREA_HA,
            "price_scale": CITE_PRICE_SCALE,
            "cost": GUARANTEE_COST,
        },
        identity_fields=["farmland_id"],
        empty_means=None,
        absence_guarantee=None,
        interpretation_guarantee=raster_interpretation + [arch_r3_05],
        source_elements=raster_elements,
        blocked_by=None,
        count=len(parcels),
        data={str(k): v for k, v in sorted(parcels.items())},
    )

    # ⛔ TECH-DEBT-103: a farm that owns land whose price cannot be computed is
    # neither "ok" (land_value is not a real figure) nor "unknown_by_design"
    # (owned_ids is non-empty -- the farm does have parcels). "partial" is the
    # honest third state: the section ran, some of its data is unavailable, and
    # the roll-up in sec. 6.3.3 already treats "partial" as outranking "ok" for
    # exactly this reason.
    if not owned_ids:
        owned_status = "unknown_by_design"
        owned_reason = "farm owns no farmland parcels on this map"
    elif owned_land_value is None:
        owned_status = "partial"
        owned_reason = (
            "at least one owned parcel declares a per-parcel price= (see "
            "farmland_parcels for which one) -- this parser "
            "computes only the derived areaInHa*pricePerHa*priceScale form, "
            "not fixedPrice, so land_value is unknown rather than a wrong "
            "derived figure")
    else:
        owned_status = "ok"
        owned_reason = None

    owned_section = _section(
        # sec. 6.3.3 status table: "the script ran; the container is present and
        # holds nothing" -> unknown_by_design + empty_means, count 0. No
        # citation is required, because the container is right there and it is
        # empty -- which is why no absence_guarantee is needed here.
        # ⛔ This was hardcoded "ok" while `empty_means` beside it was already
        # computed correctly and conditionally, so a zero-parcel farm emitted
        # `ok` + `farm_has_none` at once -- a pairing the table forbids.
        status=owned_status,
        reason=owned_reason,
        shape="record",
        capability_ids=CAPABILITY_IDS,
        typing={"total_area_ha": "float", "land_value": "float"},
        typing_guarantee={
            "total_area_ha": GUARANTEE_TOTAL_AREA_HA,
            "land_value": GUARANTEE_LAND_VALUE,
        },
        identity_fields=["parcel_ids"],
        # A farm that owns no land is a real, valid state -- F-001's mistake was
        # reading "owns nothing" as "does not exist".
        empty_means="farm_has_none" if not owned_ids else None,
        absence_guarantee=None,
        interpretation_guarantee=raster_interpretation + [arch_r3_05],
        # ELEM_CURRENT_DAY is declared here because parse_current_day() serves
        # the stored-<stats>-window coverage report about THIS section's
        # land_value figure. It never feeds a money number itself.
        source_elements=raster_elements + [ELEM_FARM_LIST, ELEM_CURRENT_DAY],
        blocked_by=None,
        count=len(owned_ids),
        data={
            "parcel_ids": owned_ids,
            "count": len(owned_ids),
            "total_area_ha": owned_total_area_ha,
            # DEC-057 (10): total_cost -> land_value. It is a current asset
            # VALUATION (area x pricePerHa x priceScale over owned parcels),
            # not a record of what was spent -- BUG-014 proved those are two
            # different questions that happened to agree.
            "land_value": owned_land_value,
        },
    )

    if fields_out is None:
        fields_section = _section(
            status="unavailable",
            reason=f"could not read fields.xml: {field_err}",
            shape="record_list", capability_ids=CAPABILITY_IDS,
            typing={}, typing_guarantee={},
            identity_fields=["field_id"],
            empty_means=None,
            absence_guarantee=None,
            interpretation_guarantee=[],
            source_elements=[ELEM_FIELD_ID],
            blocked_by=None, count=0, data=[],
        )
    else:
        # ⚖ ARCH-R3-06. Every row here rests on a MEASURED spatial join, but
        # not every row necessarily resolved -- a field with no map-side
        # polygon, an unsupported ancestor transform, or a centroid outside
        # the raster still reports null (see build_spatial_field_rows). The
        # section status follows the rows: "ok" only when every one of them
        # resolved, "partial" when at least one did not.
        unresolved = [r for r in fields_out if r["farmland_id"] is None]
        if not unresolved:
            reason = None
            status = "ok"
        else:
            status = "partial"
            reason = (
                f"{len(unresolved)} of {len(fields_out)} fields could not be "
                "spatially resolved to a farmland id (no map-side polygon, an "
                "unsupported ancestor transform, or a centroid outside this "
                "map's raster) -- see calibration_notes and "
                "interpretation_guarantee.field_coverage."
            )

        fields_section = _section(
            status=status,
            reason=reason,
            shape="record_list", capability_ids=CAPABILITY_IDS,
            # Every row carries every one of these keys -- value None where
            # a field did not resolve, exactly like parcels_section's own
            # `cost` (typed float, sometimes None per compute_parcel_cost).
            typing={"field_id": "int", "farmland_id": "int", "owned": "bool",
                    "owner_farm_id": "int", "area_ha": "float",
                    "authored_area_ha": "float", "straddles_farmland": "bool"},
            typing_guarantee={
                "field_id": CITE_FIELD_ID,
                "farmland_id": GUARANTEE_FARMLAND_ID,
                "owned": GUARANTEE_OWNED,
                "area_ha": GUARANTEE_FIELD_AREA_HA,
                "authored_area_ha": GUARANTEE_AUTHORED_AREA_HA,
                "straddles_farmland": GUARANTEE_STRADDLES_FARMLAND,
            },
            identity_fields=["field_id"],
            empty_means=None,
            absence_guarantee=None,
            interpretation_guarantee=[
                build_arch_r3_06(field_coverage, shoelace_check), arch_r3_05],
            source_elements=[ELEM_FIELD_ID, ELEM_FARMLAND_OWNER, ELEM_RASTER,
                             ELEM_MAP_I3D_FIELDS],
            blocked_by=None,
            count=len(fields_out),
            data=fields_out,
        )

    return {
        SECTION_MAP: map_section,
        SECTION_PARCELS: parcels_section,
        SECTION_OWNED: owned_section,
        SECTION_FIELDS: fields_section,
    }


def build_legacy_top_level(sections, savegame_dir, mod_zip_path, grle_name,
                           pricing_name, field_purchase_check, calibration_notes):
    """The pre-envelope top-level keys read_fields.py still consumes.

    ⚠ A DELIBERATE, RECORDED SPEC DEVIATION -- not an oversight. sec. 6.2
    defines the envelope; read_fields.py:251-266 reads top-level
    `gates_passed`, `owned.field_ids`, `owned.total_area_ha` and
    `field_purchase_cross_check`, and that file is a frozen contract this
    dispatch may not edit. Emitting the envelope alone breaks it. sec. 6.2
    closes the SECTION key list, not the top level, so both views ship.

    ⚠ RETIREMENT CONDITION: delete this function and its caller when item 10
    migrates read_fields.py onto the envelope. A shim with no stated end
    becomes architecture.

    EVERY VALUE IS READ BACK OUT OF `sections` rather than recomputed. Two
    independent computations of one number is how two views drift apart, and
    a drift here would be invisible -- the envelope would be right and the
    consumer would be wrong. test_land_domain_envelope.py asserts the two
    agree; that test is the actual guard, this docstring is only the reason."""
    owned = sections[SECTION_OWNED]["data"]
    fields_data = sections[SECTION_FIELDS]["data"]
    fields_out = fields_data if sections[SECTION_FIELDS]["status"] != "unavailable" else None
    return {
        "sources": {
            "career": os.path.join(savegame_dir, "careerSavegame.xml"),
            "farmland_ownership": os.path.join(savegame_dir, "farmland.xml"),
            "fields": os.path.join(savegame_dir, "fields.xml"),
            "map_mod_zip": mod_zip_path,
            "grle": grle_name,
            "pricing_xml": pricing_name,
        },
        "map": sections[SECTION_MAP]["data"],
        "gates_passed": sections[SECTION_MAP]["data"]["gates_passed"],
        "owned": {
            # ⛔ A COPY, NOT THE SAME LIST. This assigned by reference, so the
            # envelope's parcel_ids and the legacy block's were one mutable
            # object and a consumer editing either silently edited both. The
            # test guarding it asserted `== snapshot or 999 in ...` -- a
            # disjunction exhaustive over both possible worlds, so it passed
            # whichever way the code behaved, while the docstring above it
            # stated the requirement this line violated. Decided deliberately
            # now, in the direction the docstring already claimed.
            "parcel_ids": list(owned["parcel_ids"]),
            "count": owned["count"],
            "total_area_ha": owned["total_area_ha"],
            # DEC-057 (10) renamed this ONE site. farms_xml_fieldPurchase_abs
            # is untouched, and read_fields.py never read total_cost.
            "land_value": owned["land_value"],
            # ⛔ DEC-001, BREACHED HERE BY `or []`. fields_out is correctly None
            # when the section is unavailable; `(fields_out or [])` converted it
            # straight back to [], and read_fields.py guards exactly this case
            # with `if ids is None: return error` -- which [] disarms. The
            # consumer then returned set() while the trust note still said the
            # decode passed two gates. Both gates DID pass; they say nothing
            # about fields.xml. None propagates the absence instead.
            #
            # ⛔ BUG-016: THAT FIX WAS HALF A FIX, AND THE OTHER HALF SHIPPED THE
            # SAME DEFECT ONE BRANCH OVER. `fields_out is None` catches only
            # "could not read fields.xml". Off the ruled map the rows ARE read
            # and every `owned` is None -- ownership UNKNOWABLE, not zero -- and
            # `if f["owned"]` filtered every row out into []. Since on_ruled_map
            # is exact string equality, that was the DEFAULT path for every
            # player not on the ruled map, told with a confidence note attached
            # (DEC-071: this ships publicly).
            #
            # THREE states, not two, and the guard keys on THE ANSWER rather
            # than on the one cause of unknowability that exists today:
            #   fields_out is None      -> could not read        -> None
            #   any owned is None       -> read, unknowable      -> None
            #   otherwise               -> read, known           -> list
            # The list is legitimately [] for a farm that genuinely owns no
            # fields; that answer is real and must survive. Keying on
            # `not on_ruled_map` instead would re-break the moment a second
            # cause of unknown ownership exists.
            "field_ids": (
                None if fields_out is None
                else None if any(f["owned"] is None for f in fields_out)
                else [f["field_id"] for f in fields_out if f["owned"]]
            ),
        },
        "field_purchase_cross_check": field_purchase_check,
        "parcels": {int(k): v for k, v in sections[SECTION_PARCELS]["data"].items()},
        "fields": fields_out,
        "calibration_needed": len(calibration_notes) > 0,
        "calibration_notes": calibration_notes,
    }


class ToolkitArgumentParser(argparse.ArgumentParser):
    """argparse whose failures keep this script's machine contract: a
    structured {"error": ...} JSON on STDOUT, never argparse's default
    usage-to-stderr. --help keeps argparse's native behaviour (usage to
    stdout, exit 0).

    ⚠ THIS DOCSTRING USED TO CLAIM "exit code 1, matching every sibling
    script". BOTH HALVES WERE FALSE and the correction is comments only --
    the exit-code contract itself is deferred by DEC-065 and is a separate
    cross-cutting item, so NOTHING about the behaviour below changed.

    What is actually true, measured in this tree:
      - THIS path (an argparse failure) does emit JSON and exit 1.
      - main()'s OWN structured errors -- unresolvable mods_dir, a failed
        gate, an unknown farm_id -- emit the same shape and then `return`,
        which exits 0. So the script does not have one exit-code contract;
        it has two, and the argparse path is the minority one.
      - Siblings disagree with each other too: some exit 1 on a failed read
        and others exit 0 on the identical failure (TECH-DEBT-023, BP-007).
        "Matching every sibling script" describes a consistency that does
        not exist.
    Consumers must therefore branch on the presence of the "error" key, not
    on the exit code -- which is what read_fields.py:249 already does."""

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
             "either), resolved from --config's config.json, else a walk-up "
             "looking for sanctum/config.json -> paths.mods_dir",
    )
    parser.add_argument(
        "--config", dest="config_path", default=None, metavar="PATH",
        help="where that config.json is; if omitted, this script walks up "
             "from its own directory (item #12: that walk-up assumes a "
             "per-project install and cannot resolve on a personal one)",
    )
    # TECH-DEBT-103b: OPTIONAL. A map that ships as a mod zip needs none of
    # this -- only a BASE-GAME map (no mod zip at all, e.g. MapUS) is looked
    # up here, as a fallback when the mod-zip lookup fails. Never required,
    # never defaulted to a guessed path (F-007).
    parser.add_argument(
        "--install-dir", dest="install_dir_flag", default=None, metavar="PATH",
        help="where FS25 itself is installed, for resolving a BASE-GAME map "
             "that ships no mod zip; if omitted, resolved from --config's "
             "config.json paths.install_dir, else the same sanctum/config.json "
             "walk-up --mods-dir uses. Unresolvable is not fatal by itself -- "
             "it only matters if the mod-zip lookup fails too.",
    )
    ns = parser.parse_args(argv[1:])
    # --mods-dir (explicit flag) wins over the positional form if both given.
    mods_dir = ns.mods_dir_flag or ns.positional_mods_dir
    return ns.savegame_dir, mods_dir, ns.farm_id, ns.config_path, ns.install_dir_flag


def main():
    savegame_dir, mods_dir, farm_id, config_path, install_dir_flag = parse_args(sys.argv)

    # Check the savegame BEFORE the mods dir, because the old order reported
    # the wrong subject. find_mods_dir() ran first, so a bad savegame path
    # produced "could not locate mods_dir" -- an error about a directory the
    # user had not got wrong, naming nothing about the one they had, from a
    # script that had not yet looked at the savegame at all. The message was
    # accurate about its own failure and useless about the user's.
    if not os.path.isdir(savegame_dir):
        emit({
            "error": f"savegame_dir {savegame_dir!r} is not a directory",
            "calibration_needed": False,
        })
        return

    mods_dir, how = find_mods_dir(mods_dir, config_path)
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
    map_source_kind = "mod"
    base_map_dir = None
    base_map_dir_reason = None
    if not os.path.isfile(mod_zip_path):
        # ⛔ TECH-DEBT-103b. A missing mod zip does not necessarily mean the
        # map is unresolvable -- BASE-GAME maps (e.g. MapUS) ship no mod zip
        # at all and live on disk under <install_dir>/data/maps/<name>/
        # instead. Try that before giving up. install_dir is resolved lazily,
        # only here, so a mod-map save that never needs it pays nothing for
        # this branch existing.
        install_dir, install_dir_how = find_install_dir(install_dir_flag, config_path)
        if install_dir is not None:
            base_map_dir, base_map_dir_reason = find_base_game_map_dir(install_dir, map_id)
        else:
            base_map_dir_reason = f"install_dir not resolved: {install_dir_how}"

        if base_map_dir is None:
            available = sorted(f for f in os.listdir(mods_dir) if f.lower().endswith(".zip")) if os.path.isdir(mods_dir) else []
            emit({
                "error": (
                    f"map mod zip not found: {mod_zip_path} (derived from careerSavegame.xml mapId "
                    f"'{map_id}'). {len(available)} .zip files present in {mods_dir}. Also tried "
                    f"the base game: {base_map_dir_reason}."
                ),
                "calibration_needed": True,
                "mods_dir_zip_sample": available[:10],
            })
            return
        map_source_kind = "base_game"

    try:
        if map_source_kind == "base_game":
            zf = _DirEntries(base_map_dir)
            # `mod_zip_path` carries this domain's ONE "where the map data
            # came from" value all the way to provenance and the legacy shim
            # (build_legacy_top_level's `sources.map_mod_zip`) -- reusing the
            # variable rather than adding a second one keeps that contract
            # frozen (TECH-DEBT-103b brief: "output schema stays frozen").
            mod_zip_path = base_map_dir
        else:
            zf = zipfile.ZipFile(mod_zip_path)
    except (zipfile.BadZipFile, OSError) as e:
        emit({"error": f"could not open {mod_zip_path}: {e}", "calibration_needed": True})
        return

    namelist = zf.namelist()
    grle_name = find_zip_entry(namelist, "data/infolayer_farmlands.grle")
    pricing_name = find_zip_entry(namelist, "config/farmlands.xml")
    if not isinstance(grle_name, str):
        emit({
            "error": f"could not uniquely locate infoLayer_farmlands.grle inside {mod_zip_path}",
            "calibration_needed": True,
            "candidates": grle_name,
        })
        return
    if not isinstance(pricing_name, str):
        emit({
            "error": f"could not uniquely locate config/farmlands.xml inside {mod_zip_path}",
            "calibration_needed": True,
            "candidates": pricing_name,
        })
        return

    map_xml_name, map_width_m, map_height_m = find_map_dimensions_xml(zf, namelist)
    if map_width_m is None:
        emit({
            "error": f"could not find a top-level XML declaring <map width= height=> inside {mod_zip_path}",
            "calibration_needed": True,
        })
        return

    # TECH-DEBT-095 (HIGH). ARCH-R3-06's spatial join needs this map's own
    # field polygons. Located and read here, alongside the grle/pricing
    # reads, so the zip/dir handle can still close right after -- an
    # unresolved i3d degrades field_ownership to per-field nulls (see below)
    # rather than failing the whole run: owned_land/farmland_parcels/
    # map_calibration have nothing to do with field polygons at all.
    i3d_name, i3d_locate_reason = find_map_i3d_entry(namelist, map_xml_name)

    grle_bytes = zf.read(grle_name)
    pricing_bytes = zf.read(pricing_name)
    i3d_bytes = zf.read(i3d_name) if i3d_name else None
    zf.close()

    field_polygons = None
    fields_root_translation = (0.0, 0.0, 0.0)
    fields_root_rotation = (0.0, 0.0, 0.0)
    i3d_error = i3d_locate_reason
    if i3d_bytes is not None:
        field_polygons, fields_root_translation, fields_root_rotation, i3d_error = \
            parse_field_polygons(i3d_bytes.decode("utf-8", errors="ignore"))

    # For provenance: a mod zip is one file, hashed whole (file_provenance's
    # own docstring) -- the i3d is already inside it, so nothing more to add.
    # A base-game map has no single archive to hash the same way -- hash
    # exactly the files actually read instead, which is more precise than
    # the zip case, not less.
    map_source_paths = (
        [os.path.join(base_map_dir, grle_name), os.path.join(base_map_dir, pricing_name)]
        + ([os.path.join(base_map_dir, i3d_name)] if i3d_name else [])
        if map_source_kind == "base_game" else [mod_zip_path]
    )

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

    ownership, err, raw_id_conformance = parse_savegame_farmland_ownership(
        os.path.join(savegame_dir, "farmland.xml"))
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
    total_area_ha = pixels_to_hectares(sum(histogram.values()), area_per_pixel_m2)
    declared_area_ha = (map_width_m * map_height_m) / M2_PER_HECTARE
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
        area_ha = round(pixels_to_hectares(pixel_count, area_per_pixel_m2), 4)
        price_info = pricing.get(fid)
        cost, scale, note = compute_parcel_cost(fid, area_ha, price_per_ha, price_info, pricing_name)
        if note is not None:
            calibration_notes.append(note)
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

    owned_ids, owned_total_area_ha, owned_total_cost = compute_owned_totals(
        parcels, farm_id)

    # Reported, never used to compute a figure. See read_field_purchase_window().
    # A failure here degrades window-coverage reporting to "undetermined", so
    # it is recorded in-band rather than swallowed -- the alternative is a
    # coverage verdict of None with nothing saying why.
    current_day, current_day_err = parse_current_day(savegame_dir)
    if current_day is None:
        calibration_notes.append(
            f"could not read environment.xml <currentDay>: {current_day_err} -- "
            "stored-window coverage cannot be determined")

    # --- Cross-check against farms.xml's <fieldPurchase> -- DISABLED, DEC-057 (9) ---
    # The blocked element is not read at runtime. This is a guard, not a
    # formality: while farms_xml_fieldPurchase_abs is in the registry's
    # blocked_fields, emitting it is a tooth-2 violation, and reading its
    # source element would put farms.xml:farm/finances/stats/fieldPurchase in
    # this domain's source_elements and fire tooth 1. Leaving the corrected
    # read in place but uncalled is what lets DEFER-014 restore it by flipping
    # one flag. read_fields.py handles a null here: _ownership_source_note()
    # reports "did NOT run -- neither confirmed nor refuted", which is true.
    field_purchase_check = None
    if CROSS_CHECK_ENABLED:
        window = read_field_purchase_window(farms_root, farm_id, current_day)
        if "error" not in window:
            recorded = window["field_purchase_abs_sum"]
            field_purchase_check = dict(window)
            field_purchase_check.update({
                "computed_owned_land_value": owned_total_cost,
                "difference": round(recorded - owned_total_cost, 2),
                "match": abs(recorded - owned_total_cost) < 1.0,
            })

    # --- Field -> farmland, via ARCH-R3-06's MEASURED spatial join ------------
    # Every row carries identity_basis so a consumer can see this is a join,
    # not a coerced value, and the section carries field_coverage /
    # shoelace_label_check so "every field resolved" can be told apart from
    # "there was nothing here that could have failed" -- TECH-DEBT-095.
    field_ids, field_err = parse_savegame_field_ids(os.path.join(savegame_dir, "fields.xml"))
    fields_out = None
    shoelace_check = None
    spatial_results = {}
    if field_ids is None:
        calibration_notes.append(f"could not read fields.xml for field->farmland mapping: {field_err}")
    else:
        if field_polygons is None:
            calibration_notes.append(f"could not read this map's field polygons: {i3d_error}")
        else:
            spatial_results = resolve_spatial_field_farmland(
                field_polygons, fields_root_translation, fields_root_rotation,
                pixels, raster_width, raster_height, map_width_m, map_height_m)
            shoelace_check = build_shoelace_label_check(spatial_results)
        fields_out = build_spatial_field_rows(
            field_ids, spatial_results, parcels, farm_id, calibration_notes)

    field_coverage = build_field_coverage(
        list(field_polygons.keys()) if field_polygons is not None else None,
        field_ids)

    gates_passed = {
        "gate1_id_set_matches_savegame": True,
        "gate2_area_matches_declared_map_size": True,
    }
    map_record = {
        "map_id": map_id,
        "declared_size_m": {"width": map_width_m, "height": map_height_m},
        "raster_size_px": {"width": raster_width, "height": raster_height},
        "meters_per_pixel": mpp_x,
        "price_per_ha": price_per_ha,
        "gates_passed": gates_passed,
    }

    source_paths = [
        os.path.join(savegame_dir, "careerSavegame.xml"),
        os.path.join(savegame_dir, "farmland.xml"),
        os.path.join(savegame_dir, "farms.xml"),
        # Read every run by parse_current_day() above and previously recorded
        # in neither provenance.sources nor source_set_hash, so an edit to it
        # moved no hash and a stale cache read as fresh.
        os.path.join(savegame_dir, "environment.xml"),
        # TECH-DEBT-103b: mod_zip_path is a DIRECTORY for a base-game map, and
        # file_provenance() below requires a FILE -- appending it here would
        # silently vanish from provenance.sources (os.path.isfile() filters
        # it out with no error), which is exactly the "absence dressed as
        # completeness" shape this file exists to refuse. map_source_paths is
        # the two files actually read in that case; see its own comment.
        *map_source_paths,
    ]
    if field_ids is not None:
        source_paths.append(os.path.join(savegame_dir, "fields.xml"))
    provenance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "sources": [file_provenance(p) for p in source_paths if os.path.isfile(p)],
    }
    provenance["source_set_hash"] = source_set_hash(provenance["sources"])

    sections = build_sections(
        map_record=map_record,
        parcels=parcels,
        owned_ids=owned_ids,
        owned_total_area_ha=owned_total_area_ha,
        owned_land_value=owned_total_cost,
        fields_out=fields_out,
        field_err=field_err,
        field_coverage=field_coverage,
        # The live list, so an unresolved-field note raised inside
        # build_spatial_field_rows reaches calibration_needed in the legacy
        # block below.
        calibration_notes=calibration_notes,
        # ARCH-R3-05's per-save falsifier, read as RAW TEXT before coercion.
        raw_id_conformance=raw_id_conformance,
        # ARCH-R3-06's per-save corroboration OF THE AREA (never of the
        # join's position -- TECH-DEBT-107): does this parser's own
        # polygon-area formula reproduce the map author's printed ha label?
        shoelace_check=shoelace_check,
    )
    top_status, top_reason = roll_up(sections)

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN,
        "set": SET,
        "farm_id": farm_id,
        "capability_ids": list(CAPABILITY_IDS),
        "provenance": provenance,
        "status": top_status,
        "reason": top_reason,
        "sections": sections,
    }
    # DERIVED from the sections above -- never a second computation of the same
    # number. Gated on the flag so retiring the shim is one edit at one place,
    # and so the flag is a real switch rather than a constant that only names
    # an intention -- this file already carried one of those.
    if LEGACY_TOP_LEVEL_SHIM:
        envelope.update(build_legacy_top_level(
            sections,
            savegame_dir=savegame_dir,
            mod_zip_path=mod_zip_path,
            grle_name=grle_name,
            pricing_name=pricing_name,
            field_purchase_check=field_purchase_check,
            calibration_notes=calibration_notes,
        ))
    emit(envelope)


if __name__ == "__main__":
    main()
