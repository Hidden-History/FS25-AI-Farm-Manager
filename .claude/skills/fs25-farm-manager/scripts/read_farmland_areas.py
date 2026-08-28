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
3. FIELD -> FARMLAND MAPPING -- AN ASSUMPTION, AND IT IS NOT FALSIFIABLE HERE
===========================================================================
The savegame carries NO field->farmland link. Re-measured 2026-08-05: every
`<field>` in fields.xml has `id` plus fourteen crop-state attributes
(fruitType, growthState, weedState, ...) and NOTHING ELSE -- no area, no
position, no farmland reference, no child elements. The relationship is
spatial, and it lives in the raster this script decodes.

⛔ A FALSE ENGINE CLAIM WAS REMOVED FROM THIS DOCSTRING 2026-08-07. It read
that "a farmland answers `getField()`", cited to `FarmlandManager.md`.
`Farmland:getField` DOES NOT EXIST: at FS25 Community LUADOC @ 86f08357778f,
`docs/script/Economy/Farmland.md` (coverage.complete: true) declares exactly
five functions -- delete, load, new, setArea, setIndicatorPosition -- and none
is `getField`. The corpus's only `getField` is `AbstractFieldMission:getField()`,
a MISSION-scoped class, so it answers the join only for fields under contract
and is not a general accessor. Spec rev 8 reports the same measurement
independently. This is exactly the mis-attribution that rev 8 calls its own
most useful correction, and it had been shipping in the emitted licence text.

What the engine actually does: the join is RUNTIME-ONLY and positional. Every
ownership accessor the engine documents is keyed by world position or by
farmland id -- `getFarmlandIdAtWorldPosition`, `getFarmlandOwner`,
`getOwnedFarmlandIdsByFarmId`, `getIsValidFarmlandId` and the rest -- and none
takes a field id. `getFarmlandIdAtWorldPosition` is the engine's general answer
to this question, and it consumes a WORLD POSITION, which a savegame parser
does not have. This script is an offline parser with no `g_farmlandManager`, so
it cannot call any of them.

So the join below is an ASSUMPTION: `field_id == farmland_id`. It was derived
once (2026-07-16) from this map's `AutoDrive_config.xml` -- an external,
map-specific file -- by testing all 8 axis-orientation candidates for the
world->raster transform and keeping the only one that put every field on a
distinct, non-background parcel. It is NOT re-derived per run, and re-deriving
it would mean shipping that coordinate search here, which is out of scope.

⛔ AND THE GUARD ON IT CANNOT FIRE ON THIS MAP. The only check available
offline is "is this field id also a parcel id". Where the field ids are a
subset of the parcel ids -- which is this map -- a WRONG correspondence is
indistinguishable from a right one, so zero unmatched fields is NOT evidence
the assumption holds; it is evidence the check has nothing to catch. The
script therefore reports the assumption, its basis, and whether it was
falsifiable at all, and it never presents the join as measured:
`identity_basis` on every row, and `interpretation_guarantee` +
`id_space_overlap` on the field_ownership section. Resolving this properly is
spatial work and is deliberately NOT attempted here.

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
import os
import re
import struct
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

# ---------------------------------------------------------------- sec. 6.2 --
SCHEMA_VERSION = 1
DOMAIN = "land"
SET = "land"
GENERATOR = "read_farmland_areas.py"
GENERATOR_VERSION = "2.0.0"
CAPABILITY_IDS = ("b13", "b14")

SECTION_MAP = "map_calibration"
SECTION_PARCELS = "farmland_parcels"
SECTION_OWNED = "owned_land"
SECTION_FIELDS = "field_ownership"

# The label every field row carries so no consumer can read the join as
# measured. This replaces a docstring reference to a constant named
# FIELD_ID_EQUALS_FARMLAND_ID THAT NEVER EXISTED -- grep found the name only
# inside the prose that named it, so a reader who checked concluded the
# assumption had been removed. The assumption is real; this is its name.
IDENTITY_BASIS = "assumed_equal_id"
IDENTITY_RULE = "field_id == farmland_id"

# ⚖ ARCH-R3-04's SCOPE. The ruling is MINTED (William 2026-08-05c, spec rev 8
# sec. 6.5; DEC-070) and it is scoped to THIS MAP ONLY: "Pointed at any other
# map, the ruling is void and calibration_needed is the honest output."
# Held as a named constant rather than inline so the scope check is greppable
# and so a test can assert the licence names the map it is scoped to even when
# it does not apply.
RULED_MAP_ID = "FS25_Montana_4X.MapMontana"

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
        # DERIVED FROM THE DATA, the same construct ARCH-R3-04's sibling uses
        # (`"falsifiable": not fields.issubset(set(parcel_ids))` in
        # build_identity_overlap): true exactly where the check found a
        # contradiction, never merely where it was able to look.
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
            "retention policy for <finances><stats> is undocumented (BUG-014 "
            "sec. 6 condition 4). Where window_reaches_current_day is false the "
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


def compute_owned_totals(parcels, farm_id):
    """The owned parcel ids, their total hectares and their total value.

    ⛔ ALSO EXTRACTED FROM main() 2026-08-07, same reason. Returns a tuple so
    the three figures cannot drift apart: they are derived from one filter over
    one dict, and a test can pin the arithmetic rather than the fixture."""
    owned_ids = sorted(fid for fid, p in parcels.items()
                       if p["owner_farm_id"] == farm_id)
    total_area_ha = round(sum(parcels[fid]["area_ha"] for fid in owned_ids), 4)
    total_value = round(sum(parcels[fid]["cost"] for fid in owned_ids), 2)
    return owned_ids, total_area_ha, total_value


def build_field_rows(field_ids, parcels, farm_id, calibration_notes):
    """One ownership row per field, via the ASSUMED identity rule.

    Lives here rather than inline in main() so the honesty suite can exercise
    THE SHIPPED ROW BUILDER. An earlier draft of that suite built its own rows
    and then asserted they carried `identity_basis` -- which tested the
    fixture, not the code, and would have stayed green with the label deleted
    from this file. A test that cannot fail for a real reason is not a test.

    Appends to `calibration_notes` in place for the unmatched branch."""
    rows = []
    for field_id in field_ids:
        if field_id in parcels:
            parcel = parcels[field_id]
            rows.append({
                "field_id": field_id,
                "farmland_id": field_id,
                # The label that stops a consumer reading an assumed join as a
                # measured one. See build_identity_overlap().
                "identity_basis": IDENTITY_BASIS,
                "owned": parcel["owner_farm_id"] == farm_id,
                "owner_farm_id": parcel["owner_farm_id"],
            })
        else:
            calibration_notes.append(
                f"field id {field_id} has no matching farmland id in the decoded "
                "raster -- the field_id==farmland_id assumption does not hold for "
                "this field; reported with farmland_id=null rather than guessed")
            rows.append({
                "field_id": field_id,
                "farmland_id": None,
                "identity_basis": None,
                "owned": None,
                "owner_farm_id": None,
            })
    return rows


def build_identity_overlap(field_ids, parcel_ids):
    """Report whether the field_id == farmland_id assumption was FALSIFIABLE
    on this save -- which is a different question from whether it held.

    ⛔ THIS IS THE DEFECT THE LAND SET WAS BUILT TO FIX. The only check
    available offline is "is this field id also a parcel id". Where the field
    ids are a SUBSET of the parcel ids, that check cannot fail for any input,
    so it certifies nothing: a coincidence and a correspondence produce
    identical output. On the live save every field id is also a parcel id, so
    the historic "0 unmatched, 0 calibration notes" was the guard being unable
    to fire, and it was being read as the guard passing.

    `falsifiable` is therefore emitted next to the result. It answers "could
    this check have caught a wrong answer?", and where it is false the count
    of unmatched fields carries no evidential weight at all.

    There is no stronger check to reach for -- re-measured 2026-08-05, a
    savegame <field> carries id plus crop state and NOTHING that could refute
    a mis-join: no area, no position, no farmland reference. Making this
    detectable requires spatial resolution and is deliberately out of scope."""
    if field_ids is None:
        return {
            "checked": False,
            "reason": "fields.xml unreadable -- no field ids to check",
            "falsifiable": None,
        }
    fields = set(field_ids)
    outside = sorted(fields - set(parcel_ids))
    return {
        "checked": True,
        "rule": IDENTITY_RULE,
        "field_id_count": len(fields),
        "parcel_id_count": len(parcel_ids),
        "field_ids_outside_parcel_id_space": outside,
        "unmatched_count": len(outside),
        # The whole point. A subset means the guard has no reachable failing
        # input on this map, so its "pass" carries no information.
        "falsifiable": not fields.issubset(set(parcel_ids)),
        "note": (
            "unmatched_count is only evidence when falsifiable is true. Where "
            "the field ids are a subset of the parcel ids, a WRONG "
            "correspondence produces the same zero as a right one, so zero "
            "unmatched fields is not evidence the join is correct."
        ),
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
# carry an explicit non-schema note instead, per William's ruling 2026-08-07:
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
    "DERIVED, NOT COERCED -- the identity join's output (a field_id read as a "
    "farmland_id), not a value read from any file. The join is licensed in "
    "interpretation_guarantee (ARCH-R3-04) and never here.")
GUARANTEE_OWNED = (
    "DERIVED, NOT COERCED -- the boolean result of comparing this parcel's "
    "owner_farm_id against the queried farm_id.")

# ⚖ ARCH-R3-05 -- William 2026-08-07b, spec § 6.5 rev 10, carried under DEC-077.
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
            "field id (that reading is ARCH-R3-04's, on its own evidence). It is "
            "not a licence to aggregate, and it does not license the silent "
            "`except (KeyError, ValueError): continue` that drops a malformed row."
        ),
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
                   owned_land_value, fields_out, field_err, identity_overlap,
                   calibration_notes=None, raw_id_conformance=None):
    """The four sec. 6.2 sections this domain emits, every run.

    `calibration_notes` is the SAME list main() later hands to
    build_legacy_top_level, which derives `calibration_needed` from its
    length -- so appending here is how the scope void reaches that flag.
    Defaulted for fixtures that do not care; never skipped, only discarded.

    `raw_id_conformance` carries ARCH-R3-05's per-save falsifier. Defaulted so
    existing fixtures keep working; where it is None the ruling still ships and
    reports `falsifiable_on_this_save: null`, which is the spec's required value
    for a measurement not taken -- never `false`."""
    if calibration_notes is None:
        calibration_notes = []
    raster_elements = [ELEM_RASTER, ELEM_PRICE_PER_HA, ELEM_PRICE_SCALE,
                       ELEM_FARMLAND_ID, ELEM_FARMLAND_OWNER]

    # ⚖ ARCH-R3-04 IS SCOPED TO ONE MAP, and this is the gate that enforces it.
    # Spec: "Pointed at any other map, the ruling is void and
    # calibration_needed is the honest output." Before this gate the parser
    # applied the join unconditionally -- a confident ownership claim on a map
    # the ruling does not cover -- and the spec's own mandated "red on scope"
    # mutation had nothing to fire against. The suite's own fixtures passed
    # map_id "m" and "mapUS" and stayed green, which is the same gap seen from
    # the inside.
    on_ruled_map = map_record.get("map_id") == RULED_MAP_ID

    # ⚖ OWNER RULING, William 2026-08-07: calibration_needed DOES fire on the
    # scope void. The spec sentence quoted above names it as the honest output
    # and the gate implemented only the first half of it -- the free-text
    # `reason` said so while the one machine-readable flag a consumer branches
    # on stayed False. The unmatched-field branch below already does this
    # correctly; this is the same signal for the other way the join can fail
    # to apply. Both review lanes found the asymmetry and split on whether it
    # was a patch or a decision; it was ruled a patch.
    if not on_ruled_map:
        calibration_notes.append(
            "map %r is not %s: ARCH-R3-04 does not cover it, so no "
            "field->farmland ownership is claimed and this map needs its own "
            "calibration" % (map_record.get("map_id"), RULED_MAP_ID))

    # The area math is the engine's own, and this is a citation rather than
    # an argument: FarmlandManager:loadFarmlandData computes
    # transformFactor = terrainSize / localMapWidth, pixelToSqm =
    # transformFactor^2, ha = areaToHa(pixelCount, pixelToSqm) -- one factor
    # for BOTH axes, which is why gate 2 refuses non-square pixels rather than
    # averaging them.
    # ⚖ OWNER RULING, William 2026-08-07: NO DESIGN RULING IS INTENDED HERE, so
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
    # come back with any future object here. ARCH-R3-04 licenses the IDENTITY
    # JOIN (spec sec. 6.5), not the raster area derivation, so filling it in
    # would never have licensed this block and a reader resolving the ruling
    # would have believed otherwise.
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

    owned_section = _section(
        # sec. 6.3.3 status table: "the script ran; the container is present and
        # holds nothing" -> unknown_by_design + empty_means, count 0. No
        # citation is required, because the container is right there and it is
        # empty -- which is why no absence_guarantee is needed here.
        # ⛔ This was hardcoded "ok" while `empty_means` beside it was already
        # computed correctly and conditionally, so a zero-parcel farm emitted
        # `ok` + `farm_has_none` at once -- a pairing the table forbids.
        status="unknown_by_design" if not owned_ids else "ok",
        reason=("farm owns no farmland parcels on this map" if not owned_ids else None),
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
        # ⛔ B3: OFF THE RULED MAP THE LICENCE IS VOID, so the rows must stop
        # claiming an ownership answer too. Voiding the licence while leaving
        # `owned: true` on every row would move the dishonesty rather than
        # remove it. Done here, in one place, so the licence and the rows can
        # never disagree about whether the join applied.
        if not on_ruled_map:
            fields_out = [
                {**row, "farmland_id": None, "identity_basis": None,
                 "owned": None, "owner_farm_id": None}
                for row in fields_out
            ]

        # A3: the reason is DERIVED from the per-save falsifiability, never
        # hardcoded. It previously asserted "could not falsify on this save"
        # unconditionally while `falsifiable` was computed per save, so on a
        # non-subset save the section contradicted itself.
        falsifiable = identity_overlap.get("falsifiable")
        if not on_ruled_map:
            reason = (
                f"ARCH-R3-04 does not cover map {map_record.get('map_id')!r} -- the "
                f"ruling is scoped to {RULED_MAP_ID}. The identity "
                f"{IDENTITY_RULE} is NOT applied here and no field->farmland "
                "ownership is claimed; calibration is needed for this map."
            )
        elif falsifiable:
            reason = (
                "field->farmland ownership rests on the identity "
                f"{IDENTITY_RULE}, licensed by ARCH-R3-04 and not re-derived "
                "per run. On this save the id-space check WAS falsifiable and "
                "unmatched fields are reported (see "
                "interpretation_guarantee.id_space_overlap)."
            )
        else:
            reason = (
                "field->farmland ownership rests on the identity "
                f"{IDENTITY_RULE}, licensed by ARCH-R3-04, which this script "
                "does not re-derive and could not falsify on this save (see "
                "interpretation_guarantee.id_space_overlap)."
            )

        fields_section = _section(
            # PARTIAL, NOT OK, AND THIS IS THE HONEST STATUS. Every row here
            # rests on a DESIGN RULING, not a measurement: ARCH-R3-04 is
            # `kind: design_ruling` permanently and carries
            # falsifiable_on_this_save: false. "ok" would read as a measured
            # join. sec. 6.5's worked example shows "ok", but it names the
            # section "fields" where this domain ships "field_ownership", so it
            # is illustrative rather than a key-by-key mandate -- and neither
            # review lane raised the status. FLAGGED for the step-4 review
            # rather than flipped here, because it changes the domain roll-up
            # every consumer sees.
            status="partial",
            reason=reason,
            shape="record_list", capability_ids=CAPABILITY_IDS,
            # ⛔ DECLARE WHAT IS ACTUALLY EMITTED. This declared four
            # non-nullable types unconditionally, while off the ruled map the
            # scope gate sets farmland_id, identity_basis, owned and
            # owner_farm_id to None on EVERY row -- so `owned: "bool"` described
            # a NoneType, universally rather than occasionally, and
            # typing_guarantee ({}) licensed nothing. sec. 6.5 rule 3's
            # un-claiming default again: off-map only field_id survives as a
            # typed value, so only field_id is declared. Sibling suites enforce
            # typing-vs-data conformance and would have caught this.
            typing=({"field_id": "int", "farmland_id": "int",
                     "owned": "bool", "owner_farm_id": "int"}
                    if on_ruled_map else {"field_id": "int"}),
            # MIRRORS `typing` ABOVE, and must keep mirroring it: off the ruled
            # map the scope gate nulls every field but field_id, so only
            # field_id survives as a typed value and only it carries a
            # guarantee. Declaring more here than `typing` declares would
            # re-create the defect the comment above describes, one key over.
            # `owner_farm_id` is absent because typing_guarantee is citations
            # only and its licence is ARCH-R3-05, in interpretation_guarantee
            # below -- see the note beside the constants.
            typing_guarantee=({
                "field_id": CITE_FIELD_ID,
                "farmland_id": GUARANTEE_FARMLAND_ID,
                "owned": GUARANTEE_OWNED,
            } if on_ruled_map else {"field_id": CITE_FIELD_ID}),
            identity_fields=["field_id"],
            empty_means=None,
            absence_guarantee=None,
            # ⚖ SAME OWNER RULING, fourth section. Off the ruled map this
            # emitted `kind: "design_ruling"` with `ruling: None` -- the same
            # undefined middle state as the raster block, and by sec. 6.5 rule 2
            # a design_ruling that names no ruling is a build failure. Off-map
            # the section now takes rule 3's un-claiming default and reports
            # what it observed without the interpretation.
            #
            # ⚠ What a consumer uses instead, off-map: `reason` names the map
            # and says the join was not applied, and `calibration_needed` is now
            # true (the companion ruling above). The rows themselves carry
            # `owned: None`. Nothing that mattered was load-bearing on this
            # object -- no script reads interpretation_guarantee at all; it is
            # asserted only by the suites.
            # ⚖ DEC-077 / § 6.2.1 -- A LIST, and the two rulings have DIFFERENT
            # SCOPES, which is the whole reason the shapes differ here:
            #   ARCH-R3-04 is MAP-SCOPED  -> stays inside the on_ruled_map
            #                                conditional; off-map the list simply
            #                                does not contain it.
            #   ARCH-R3-05 is FILE-WIDE   -> appended OUTSIDE the conditional, so
            #                                it is present on every save.
            # ⛔ ARCH-R3-04's object below is WRAPPED, not retyped and not
            # rewritten. Merging the two into one entry is § 6.2.1 rule 3's
            # forbidden case: two rulings with different falsifiers under one id
            # cannot be refuted independently, and refuting either would appear
            # to refute both.
            interpretation_guarantee=([] if not on_ruled_map else [{
                # ⛔ kind is design_ruling PERMANENTLY and may NEVER be
                # relabelled schema_cited. The available substitute is a census
                # of conforming ids, and a census is INDUCTION, never a
                # citation (spec sec. 6.5).
                "kind": "design_ruling",
                # ⚖ MINTED -- William 2026-08-05c (spec rev 8 sec. 6.5, DEC-070).
                # This shipped as `ruling: None` + `ruling_status: "UNMINTED"`
                # while the ruling was already minted, and a test PINNED that
                # declaration, so the suite went red on the correct fix and
                # stayed green on the defect. Voided off-map -- see below.
                # Unconditional: this object now exists ONLY on the ruled map,
                # so the ruling always resolves. The `if on_ruled_map else None`
                # that used to sit here was the null-ruling state itself.
                "ruling": "ARCH-R3-04",
                # The map the ruling is scoped to, kept so a reader can see what
                # the licence is bounded by without resolving the id.
                "map_id": RULED_MAP_ID,
                # ⚖ OWNER RULING, William 2026-08-07: THE PER-SAVE MEASUREMENT
                # WINS, so this is DERIVED and never hardcoded.
                # It shipped as a bare `False` three lines from a `reason` that
                # the A3 fix had already made per-save, so on a non-subset save
                # the same JSON object reported that the id-space check FIRED
                # and that it CANNOT fire. A3 fixed one of three siblings; this
                # is the other two. The spec's mutation table still mandates the
                # literal `false` -- the spec is being corrected to match the
                # measurement, not the measurement bent to match the spec.
                "falsifiable_on_this_save": falsifiable,
                "text": (
                    f"{IDENTITY_RULE}: a field id from fields.xml is read as the "
                    "id of the farmland parcel containing that field, on "
                    f"{RULED_MAP_ID} ONLY. The reading is a DECISION, not a "
                    "measurement. The engine exposes this join only at RUNTIME "
                    "(FarmlandManager:getFarmlandIdAtWorldPosition), and it is "
                    "uncallable from a savegame parser. fields.xml carries id "
                    "plus 14 crop-state attributes and no position, area or "
                    "farmland reference, so NO data in the savegame can "
                    "contradict this reading. "
                    # ⚖ Same ruling, same reason: this sentence asserted a
                    # SUBSET RELATION THAT IS FALSE on a non-subset save, in the
                    # licence text a reader trusts most.
                    + (
                        "On this save the field ids are NOT a strict subset of "
                        "the parcel ids, so the range guard's else branch IS "
                        "reachable and the unmatched fields reported in "
                        "id_space_overlap are real evidence (sec. 6.5)."
                        if falsifiable else
                        "On this save the field ids are a strict subset of the "
                        "parcel ids, so the range guard's else branch is "
                        "unreachable and '0 unmatched' is NOT evidence of "
                        "correctness (sec. 6.5)."
                    )
                ),
                # ⛔ CORROBORATION, HELD NON-LICENSING -- the sec. 6.3.4 pattern.
                # It rests on a third-party mod artifact AND on the GRLE decoder
                # BUG-014 sec. 8 records as never independently re-validated, so
                # it shares a dependency with the component most likely to be
                # wrong and cannot falsify itself.
                "corroboration_non_licensing": (
                    "Derived once on 2026-07-16 from this map's AutoDrive_config.xml "
                    "(122 'Feld N' mapmarkers) against the GRLE raster, transform "
                    "selected from 8 candidates, yielding 122/122 farmland_id == "
                    "field_id with zero collisions. This CORROBORATES the ruling and "
                    "is deliberately held NON-LICENSING: it is a third-party artifact "
                    "plus a decoder BUG-014 sec. 8 records as never independently "
                    "re-validated, and it is not re-derived per run."
                ),
                "id_space_overlap": identity_overlap,
            }]) + [arch_r3_05],
            source_elements=[ELEM_FIELD_ID, ELEM_FARMLAND_OWNER, ELEM_RASTER],
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
    ns = parser.parse_args(argv[1:])
    # --mods-dir (explicit flag) wins over the positional form if both given.
    mods_dir = ns.mods_dir_flag or ns.positional_mods_dir
    return ns.savegame_dir, mods_dir, ns.farm_id, ns.config_path


def main():
    savegame_dir, mods_dir, farm_id, config_path = parse_args(sys.argv)

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

    # --- Field -> farmland -> ownership, via the ASSUMED identity rule --------
    # Every row carries identity_basis so no consumer can read the join as
    # measured, and the section carries id_space_overlap so "0 unmatched" can
    # never again be read as "0 problems". See build_identity_overlap().
    field_ids, field_err = parse_savegame_field_ids(os.path.join(savegame_dir, "fields.xml"))
    fields_out = None
    if field_ids is None:
        calibration_notes.append(f"could not read fields.xml for field->farmland mapping: {field_err}")
    else:
        fields_out = build_field_rows(field_ids, parcels, farm_id, calibration_notes)

    identity_overlap = build_identity_overlap(field_ids, set(parcels))

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
        mod_zip_path,
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
        identity_overlap=identity_overlap,
        # The live list, so a scope-void note raised inside build_sections
        # reaches calibration_needed in the legacy block below.
        calibration_notes=calibration_notes,
        # ARCH-R3-05's per-save falsifier, read as RAW TEXT before coercion.
        raw_id_conformance=raw_id_conformance,
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
