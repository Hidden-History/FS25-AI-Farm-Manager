"""
Shared helpers for reading Farming Simulator 25 savegame XML files.

Design principle: FS25's exact XML schema can vary slightly by file and by
map mods, and hasn't been independently verified byte-for-byte here. So every
parser in this skill does two things:

1. Best-effort extraction of the fields we expect (based on documented/
   community-confirmed structures for fields.xml, economy.xml, missions.xml).
2. A full generic dump of the XML as nested JSON, included alongside, so nothing
   is silently lost if a tag name is slightly different than expected.

If you (Claude, running this skill for real) see the generic dump contain data
that the "expected fields" section missed, prefer the generic dump and note in
the briefing that the parser should be calibrated -- see SKILL.md "Calibration".
"""
import xml.etree.ElementTree as ET
import json
import re
import sys
import os
import time
import zipfile

# FS25 autosaves while the game is running -- the savegame is NOT frozen
# until the player manually saves (confirmed live: environment.xml mtime
# was 76s old with the game open; farm cash moved 88,575,568 -> 88,575,504
# mid-session with no sale to explain it). See FRICTION-LOG.md F-016.
#
# That means a parser can catch a save file mid-write. Two distinct hazards
# follow from that, and load_xml() below defends against both:
#
#   1. A torn read that breaks XML syntax (unclosed tag, truncated element).
#      This is the common case and is self-announcing: ET raises ParseError.
#      Bounded retries turn this transient failure into a clean success once
#      the writer finishes, or a clean error if it doesn't.
#
#   2. A torn read that DOESN'T break XML syntax -- e.g. an in-place,
#      non-atomic overwrite where the reader's read straddles old and new
#      bytes, and the old bytes happen to close out the document validly.
#      This is the dangerous one: syntactically valid XML with silently
#      wrong data (a stale attribute value, a hybrid old/new record, a
#      wrong record count). Verified reproducible offline: simulating an
#      in-place overwrite of a 3-record farmland.xml, 199/234 (85%) of
#      possible truncation points still parsed as valid XML, including a
#      corrupted hybrid record blending a new attribute with a stale one.
#      ET's own well-formedness check does NOT catch this -- so load_xml
#      reads the file TWICE with a short pause and requires the bytes to be
#      byte-identical before trusting them at all. A write in progress will
#      not produce identical bytes on both reads.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.2
STABILITY_CHECK_DELAY_SECONDS = 0.08


def xml_to_dict(elem):
    """Recursively convert an ElementTree element into a plain dict/list structure."""
    node = {}
    if elem.attrib:
        node["@attrs"] = dict(elem.attrib)
    children = list(elem)
    if children:
        child_groups = {}
        for child in children:
            child_groups.setdefault(child.tag, []).append(xml_to_dict(child))
        for tag, group in child_groups.items():
            node[tag] = group if len(group) > 1 else group[0]
    text = (elem.text or "").strip()
    if text:
        node["#text"] = text
    return node


def _read_stable_bytes(path):
    """Read a file's bytes twice with a short pause and require them to match.

    A single read (even one that parses as well-formed XML) is not proof the
    file wasn't caught mid-write -- see the module docstring note above on
    non-atomic in-place overwrites. Two reads that agree byte-for-byte is a
    much stronger guarantee than "it parsed" or "mtime looks stable" (mtime
    resolution/caching on this project's 9p/DrvFs mount under WSL is not
    trustworthy for sub-second writes).

    Returns (bytes, None) on a stable read, or (None, error_message) if the
    file is actively changing, unreadable, or empty.
    """
    try:
        with open(path, "rb") as f:
            first = f.read()
        time.sleep(STABILITY_CHECK_DELAY_SECONDS)
        with open(path, "rb") as f:
            second = f.read()
    except OSError as e:
        return None, f"could not read {path}: {e}"

    if first != second:
        return None, f"file changed while being read (mid-write): {path}"
    if len(first) == 0:
        return None, f"file is empty (0 bytes): {path}"
    return first, None


def load_xml(path):
    """Parse an XML file and return (root_element, generic_dict) or (None, {'error': ...}).

    Bounded-retries a torn/concurrent read (see RETRY_ATTEMPTS): FS25
    autosaves while running, so a parser can catch a save file mid-write. A
    torn read is transient -- the file is complete again milliseconds later
    -- so a short bounded retry turns what would otherwise be a hard failure
    into a clean success, without risking an infinite spin: a persistently
    malformed file simply exhausts its retries (~3 attempts, well under a
    second total) and returns the same clean error shape as before.
    """
    if not os.path.isfile(path):
        return None, {"error": f"file not found: {path}"}

    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        data, stability_error = _read_stable_bytes(path)
        if stability_error:
            last_error = stability_error
        else:
            try:
                root = ET.fromstring(data)
                return root, {root.tag: xml_to_dict(root)}
            except ET.ParseError as e:
                last_error = f"XML parse error in {path}: {e}"
            except Exception as e:
                # Must not let a genuinely unexpected condition crash the
                # caller with a bare traceback -- always hand back a clean,
                # unambiguous error instead.
                last_error = f"unexpected error parsing {path}: {type(e).__name__}: {e}"

        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS)

    return None, {
        "error": f"{last_error} (persisted across {RETRY_ATTEMPTS} attempts)",
    }


def emit(result):
    """Print a result dict as JSON to stdout (the standard output contract for these scripts)."""
    print(json.dumps(result, indent=2))


def arg_or_exit(usage):
    if len(sys.argv) < 2:
        print(json.dumps({"error": f"usage: {usage}"}))
        sys.exit(1)
    return sys.argv[1]


# ---------------------------------------------------------------------------
# THE SHARED TYPE-XML RESOLVER (plan item (1)a)
#
# WHY IT LIVES HERE AND NOT IN A NEW FILE. check_skill_honesty.py:559 fails the
# build for any scripts/*.py that SKILL.md does not name, exempting only
# __init__.py, xml_utils.py and check_skill_honesty.py. So this module is the
# only place in scripts/ where a shared, multi-consumer helper can land without
# editing SKILL.md -- a file with four other pending editors. That is a real
# design constraint, not a preference.
#
# WHY IT IS SHARED AT ALL. The savegame gives numerators and never denominators:
# `capacity=` appears 18 times in the whole of this save's placeables.xml and 16
# of them are 0.0. Every capacity -- and so every low-capacity warning -- needs
# the placeable's `filename=` joined to its own type XML. Six areas need that one
# join (silos, bunker silos, object storage, barn feed, livestock outputs, fuel).
# Six private copies of it would drift; one would not.
#
# THIS IS A MOVE, NOT A REWRITE. The body below came from
# read_store_prices._load_root_for_filename, which had been carrying it since
# 2026-07-24 for store prices and fuel capacity. It was verified working against
# this save before it was moved (all four husbandry placeables resolve), and
# read_store_prices now delegates here so there is exactly one copy. Rebuilding
# it would have thrown away the F-019 hardening below.
#
# ==> RESOLVE THE PATH, NEVER THE BASENAME (F-019). <==
# A "$moddir$<Mod>/..." filename lives ONLY inside that mod's zip. A resolver
# that falls back to searching the base install by basename returns a PLAUSIBLE,
# WRONG answer, because mods routinely reuse base-game basenames:
#     seriesX9.xml, northStar1230FB.xml, vnx300.xml
# all exist BOTH in the base install and inside a mod zip on this very save. In
# this save the three happen to carry the same price, which is exactly what makes
# the failure mode dangerous -- a basename resolver is right here by luck and
# wrong the moment a mod changes the numbers. The same trap is live for barns:
# two different mods can each ship a `cowBarnBig.xml`, and matching on the name
# returns a capacity wrong by an order of magnitude.
#
# So: an exact full-path match inside the zip, or a typed failure. Never a
# near-match, never a search.
MODDIR_RE = re.compile(r"^\$moddir\$([^/]+)/(.+)$")
DATA_PREFIX_RE = re.compile(r"^\$?data/(.+)$")


def resolve_game_xml(filename, install_dir, mods_dir):
    """Resolve a savegame-style `filename=` to its parsed type XML.

    Returns (root_or_None, source_label_or_None, resolution_kind, error_or_None).

    `resolution_kind` is one of "base", "mod", "unresolved" and is ALWAYS set,
    even on error, so a caller can tally outcomes without re-deriving them from
    the error string. A failure returns a reason, never None-as-data: DEC-001
    applies to this join like everything else, and "the type XML could not be
    opened" must never render as "this barn has no capacity".

    ⚠ PDLC placeables are a known unreadable class: `.dlc` files make
    zipfile raise BadZipFile. That surfaces here as a typed "mod" failure with
    the exception's own words, which is the correct outcome -- not a crash, and
    not a silent zero.
    """
    if not filename:
        return None, None, "unresolved", "empty filename"

    mod_match = MODDIR_RE.match(filename)
    if mod_match:
        mod_name, inner_path = mod_match.group(1), mod_match.group(2)
        if not mods_dir:
            return None, None, "mod", (
                f"{filename!r} is a $moddir$ path but no mods directory was given, "
                f"so it cannot be resolved. Not falling back to the base install: "
                f"a $moddir$ file is not there (F-019)."
            )
        zip_path = os.path.join(mods_dir, mod_name + ".zip")
        if not os.path.isfile(zip_path):
            return None, None, "mod", f"mod zip not found: {zip_path}"
        try:
            with zipfile.ZipFile(zip_path) as z:
                names = z.namelist()
                # Exact full-path match only -- see F-019 above.
                match = inner_path if inner_path in names else None
                if match is None:
                    # Case-insensitive, still on the FULL PATH. Mod authors are
                    # inconsistent about case; they are not inconsistent about
                    # directory structure. This relaxes case, never structure.
                    lower_map = {n.lower(): n for n in names}
                    match = lower_map.get(inner_path.lower())
                if match is None:
                    return None, None, "mod", (
                        f"{inner_path!r} not found inside {zip_path} "
                        f"(zip has {len(names)} entries; not falling back to a "
                        f"basename search inside the zip)."
                    )
                data = z.read(match)
        except (zipfile.BadZipFile, KeyError, OSError) as e:
            return None, None, "mod", f"could not read {inner_path!r} from {zip_path}: {e}"

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            return None, None, "mod", f"XML parse error in {zip_path}!{inner_path}: {e}"

        return root, f"{mod_name}.zip!{inner_path}", "mod", None

    data_match = DATA_PREFIX_RE.match(filename)
    if data_match or filename.startswith("data/"):
        rel = data_match.group(1) if data_match else filename[len("data/"):]
        if not install_dir:
            return None, None, "base", (
                f"{filename!r} is a base-install path but no install directory "
                f"was given, so it cannot be resolved."
            )
        full_path = os.path.join(install_dir, "data", rel)
        if not os.path.isfile(full_path):
            return None, None, "base", f"base install file not found: {full_path}"
        root, generic = load_xml(full_path)
        if root is None:
            return None, None, "base", f"could not parse {full_path}: {generic.get('error')}"
        return root, full_path, "base", None

    return None, None, "unresolved", (
        f"filename {filename!r} matches neither '$moddir$<ModName>/...' nor "
        f"'data/...'/'$data/...' -- unrecognized pattern, not resolved."
    )


def read_husbandry_capacities(root):
    """The declared capacities on a husbandry placeable's TYPE XML.

    Returns a dict. Every value is either a number or None-with-a-reason
    alongside it in `unreadable`; a capacity this function cannot read is named,
    never omitted -- an omitted ceiling reads as "no limit", which is the
    DEC-001 failure one level up from an empty list.

        food_capacity        <food capacity=>            litres of feed the barn holds
        max_num_animals      <animals maxNumAnimals=>    the herd ceiling
        animal_type          <animals type=>             COW / SHEEP / CHICKEN / ...
        output_capacities    {fillType: capacity}        from <capacity fillType= capacity=>
        unreadable           [ {what, raw, reason} ]     every value that would not coerce

    ⚠ A DECLARED ZERO IS A REAL ZERO, NOT AN ABSENCE. cowBarnBig declares
    MANURE capacity 0 while declaring MILK 300000 -- the barn genuinely holds no
    manure. Dropping zeros here would silently delete a true fact and make a
    full manure store unrepresentable.
    """
    result = {
        "food_capacity": None,
        "max_num_animals": None,
        "animal_type": None,
        "output_capacities": {},
        "unreadable": [],
    }

    def _number(raw, what):
        try:
            return float(raw)
        except (TypeError, ValueError):
            result["unreadable"].append({
                "what": what, "raw": raw,
                "reason": "declared in the type XML but is not a number",
            })
            return None

    food = root.find(".//food")
    if food is not None and "capacity" in food.attrib:
        result["food_capacity"] = _number(food.attrib["capacity"], "food@capacity")

    animals = root.find(".//animals")
    if animals is not None:
        result["animal_type"] = animals.attrib.get("type")
        if "maxNumAnimals" in animals.attrib:
            value = _number(animals.attrib["maxNumAnimals"], "animals@maxNumAnimals")
            result["max_num_animals"] = int(value) if value is not None else None

    for node in root.iter("capacity"):
        fill_type = node.attrib.get("fillType")
        if not fill_type or "capacity" not in node.attrib:
            continue
        value = _number(node.attrib["capacity"], f"capacity[{fill_type}]@capacity")
        if value is not None:
            result["output_capacities"][fill_type] = value

    return result
