"""
DOMAIN SCRIPT (b1, b2, b7, b8, b20, b21, b24) -- production DEFINITIONS, emitted
in the sec. 6.2 domain envelope.

Usage: python3 read_production_defs.py [<savegame_dir>] [--farm-id N]
                                       [--config PATH] [--install-dir PATH]
                                       [--mods-dir PATH]

Built against architecture-farm-manager-cached-state.md rev 4. The third script
of the `production` set, and the only one that does NOT read the savegame.

    b1   map-mod placeable defs   <productionPoint><production><inputs>/<outputs>
    b2   base-game placeable defs same
    b7   both                     <productionPoint><storage><capacity fillType capacity>
    b8   base-game greenhouses    <greenhouse><plants><plant> + <productionPoint>
    b20  base-game bale defs      <bale><fillType capacity mass supportsWrapping> + <fermenting>
    b21  maps_bales.xml x2        <bales><bale filename isAvailable>
    b24  base-game pallet defs    vehicle type="pallet" <fillUnit fillTypes capacity>

WHY THIS IS A SEPARATE SCRIPT AND NOT MORE SECTIONS ON read_productions.py
---------------------------------------------------------------------------
Different source surface, different reader class, different failure modes.
read_productions.py opens ONE savegame file and answers "what is this farm's
factory doing right now". This opens the GAME INSTALL and a 1 GB MOD ZIP and
answers "what can this equipment do at all" -- a question with no farm in it.
A savegame reader that could not find the install would fail for a reason that
has nothing to do with the savegame, and one commit spanning both would be hard
to review and hard to unpick.

⛔ THIS IS THE HALF THAT MAKES "SILO FULL" COMPUTABLE, AND THAT IS b7's WHOLE POINT
-----------------------------------------------------------------------------------
The savegame records what a production storage HOLDS; only the placeable's
definition records what it CAN hold. read_productions.py's storage_fill_levels
section says so in its own reason and refuses to imply a ratio. This script
supplies the missing half: `storage_capacities` below carries the ceiling.
Neither script computes the ratio -- they are separate domains and the join
belongs to whatever consumes both, which is the layer that also has to decide
what "full" means.

⚠ KEY BY FULL PATH, NEVER BY BASENAME -- AND THE DUPLICATE IS REAL
--------------------------------------------------------------------
sec. 6.5's hazard table warns that `maps_bales.xml` exists twice with disjoint
values. MEASURED on this machine, and the duplicate is confirmed:

    <install>/data/maps/maps_bales.xml        11 <bale>
    <mods>/FS25_Montana_4X.zip!mapUS/config/maps_bales.xml   19 <bale>

So a reader keying on the basename collides two different files. Every row this
script emits therefore carries `source_path`, the FULL path including the
`zip!member` form, and rows are never merged across paths.

⚠ TWO FIGURES IN THE SPEC DO NOT REPRODUCE, and they are reported rather than
quietly followed:

  * sec. 6.5 says "87 add/remove diffs" between those two files. MEASURED: the
    symmetric difference is **8**, under three independent readings (full
    attribute tuples, filenames only, every element+attrs).
  * sec. 6.5 calls them "disjoint values". They are NOT disjoint -- `only in
    base` is **0**, so the mod set is a strict SUPERSET: it adds 8 bales and
    removes none.

The rule's CONCLUSION -- key by full path -- is right and is followed. Its
figure and its characterisation are wrong, and this script does not restate
either. Both are routed to team-lead as a spec defect.

PROVENANCE DEVIATES FROM sec. 2.1's ONE-RECORD-PER-FILE SHAPE, DELIBERATELY
---------------------------------------------------------------------------
This domain reads **305** definition files (254 from the install, 51 from the
mod) against read_livestock.py's one. sec. 2.1's `sources[]` carries one record
per file, which at this scale would put 305 records in front of every consumer
and drown the envelope it is supposed to describe.

So `sources[]` carries ONE RECORD PER ROOT -- the install tree and the mod zip
-- each with `file_count` and a `sha256` that is a SET HASH over that root's
`relative_path\0sha256` lines. Nothing is weakened: any file changing, being
added, or being removed still moves that root's hash and therefore
`source_set_hash`. What is lost is per-file attribution inside a root, which no
consumer of this domain has asked for.

Stated here rather than done silently, and reported as a spec-shape gap: sec. 2.1
was written for a handful of savegame files and does not say what a domain
reading hundreds should do.

WHAT IS NOT HERE
-----------------
Nothing farm-specific. Definitions are identical for every farm on a save, so
`--farm-id` is accepted for interface consistency with the other domain scripts
and recorded in the envelope, but it FILTERS NOTHING. Each section says so.

c5 (production cycle progress) and c7 (greenhouse plant growth stage) are
absent from this script as well as from read_productions.py, and for a
different reason: they are runtime state, so no DEFINITION file could carry
them either. `greenhouse_recipes` reports a greenhouse's plant SLOTS and its
economics, never a growth stage.

Output contract:
    - Could-not-run -- the install or mods directory cannot be resolved or does
      not exist -- emits a top-level {"error": ...} and exits 1 (sec. 6.3,
      DEC-001). Never [], never {}, never None. It NEVER falls back to a
      hardcoded Windows/WSL path guess; that mistake is FRICTION-LOG.md F-007.
    - The script ran -- the envelope is emitted with all six sections always
      present, each with its own status.
"""
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import emit

SCHEMA_VERSION = 1
GENERATOR = "read_production_defs.py"
GENERATOR_VERSION = "1.0.0"
USAGE = ("read_production_defs.py [<savegame_dir>] [--farm-id N] [--config PATH] "
         "[--install-dir PATH] [--mods-dir PATH]")

DOMAIN = "production_defs"
SET = "production"
CAPABILITY_IDS = ["b1", "b2", "b7", "b8", "b20", "b21", "b24"]

# Where definitions live under the install. Globbed rather than hardcoded per
# file, because the base game ships 503 placeable XMLs and the interesting
# subset is decided by CONTENT, not by name.
INSTALL_SUBTREES = (
    ("placeables", ("data", "placeables")),
    ("pallets", ("data", "objects", "pallets")),
    ("bales", ("data", "objects", "bales")),
)
INSTALL_MAPS_BALES = ("data", "maps", "maps_bales.xml")

# A definition file is only opened once; these decide whether it is KEPT.
INTERESTING = (b"<production ", b"<capacity ", b"<bale ", b"<fillUnit ",
               b"<fillType ")

_ABSENT = object()


def build_row(pairs, defaulted=()):
    """(key, value) pairs -> a row with absent values OMITTED, not nulled.

    Same mechanism, and the same reason, as read_bales_pallets.py: `{"x": null}`
    reads as "this thing HAS no x" when the fact is "the attribute was not in
    the file". DEC-001, one level in. An absent attribute is dropped and named
    in `absent_attributes`, so a consumer gets a loud KeyError rather than a
    null that is indistinguishable from a real one.

    `defaulted` names attributes the SOURCE FILE did not carry but whose value is
    supplied by an XSD `default=`. Those are VALUES BY CITATION, not absences --
    savegame_vehicles.xsd:1103 declares baleTypeIndex default="1", so an absent
    attribute IS 1 and the row must say 1, not omit the key.

    ⚠ THEY ARE STILL NOT OBSERVED, AND THAT IS WHY THEY ARE NAMED. A defaulted
    value and a value read from the file are different provenance, and this
    codebase recorded that difference THREE DIFFERENT WAYS before this field
    existed: read_productions.py carried a per-field `fill_level_was_defaulted`
    boolean, this script recorded its three cited defaults with NOTHING AT ALL,
    and read_production_defs.py had no defaults to record. Two scripts, two
    answers to one question, with 37 builders still to come -- the same opt-in
    failure `absent_attributes` exists to close, one category over.
    """
    row, absent = {}, []
    for key, value in pairs:
        if value is _ABSENT:
            absent.append(key)
        else:
            row[key] = value
    row["absent_attributes"] = absent
    row["defaulted_attributes"] = sorted(defaulted)
    return row


def opt(attrib, name):
    return attrib[name] if name in attrib else _ABSENT


def fail(message, **extra):
    """Top-level could-not-run: structured error, exit 1 (sec. 6.3, DEC-001).

    Every message is deliberately distinct -- byte-identical duplicate errors
    are what defeated a mutation harness in TECH-DEBT-021 item 1.
    """
    payload = {"error": message}
    payload.update(extra)
    emit(payload)
    sys.exit(1)


def parse_args(argv):
    """Returns (farm_id, config, install_dir, mods_dir, error_or_None).

    AN UNRECOGNISED ARGUMENT IS AN ERROR, and that is not the house style
    everywhere: read_equipment_market.py's parse_path_args ends its loop with a
    bare `i += 1`, so a misspelt flag is silently dropped. That is the H3 defect
    read_livestock.py carries a note on, and it is not repeated here.

    The leading positional is accepted and IGNORED. It exists so this script has
    the same call shape as every other entry in collect_state.py's PARSERS
    table, which passes <savegame_dir> to everything. Definitions are
    farm-independent, so there is nothing in the savegame for this script to
    read -- and saying that out loud is better than accepting a path and
    implying it matters.
    """
    farm_id, config, install_dir, mods_dir = 1, None, None, None
    args = list(argv[1:])
    if args and not args[0].startswith("-"):
        args = args[1:]  # the ignored positional
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--farm-id", "--config", "--install-dir", "--mods-dir"):
            if i + 1 >= len(args):
                return None, None, None, None, f"{arg} given with no value"
            value = args[i + 1]
            i += 2
        elif "=" in arg and arg.split("=", 1)[0] in (
                "--farm-id", "--config", "--install-dir", "--mods-dir"):
            arg, value = arg.split("=", 1)
            i += 1
        else:
            return None, None, None, None, (
                f"unrecognised argument {arg!r} -- refusing to ignore it. "
                f"usage: {USAGE}")
        if arg == "--farm-id":
            try:
                farm_id = int(value)
            except ValueError:
                return None, None, None, None, (
                    f"--farm-id must be an integer, got {value!r}")
        elif arg == "--config":
            config = value
        elif arg == "--install-dir":
            install_dir = value
        else:
            mods_dir = value
    return farm_id, config, install_dir, mods_dir, None


def load_paths(config, install_dir, mods_dir):
    """Resolve (install_dir, mods_dir, error_or_None).

    Explicit flags win. Otherwise a config.json's "paths" block, defaulting to
    sanctum/config.json relative to cwd -- this skill's convention. NEVER falls
    back to a hardcoded Windows/WSL path guess (FRICTION-LOG.md F-007).
    """
    if install_dir and mods_dir:
        return install_dir, mods_dir, None
    config_path = config or os.path.join("sanctum", "config.json")
    if not os.path.isfile(config_path):
        return None, None, (
            f"no --install-dir/--mods-dir given and no config at {config_path!r}. "
            "Pass them explicitly, or --config pointing at a config.json with a "
            "'paths' block. Refusing to guess an install location.")
    try:
        with open(config_path, encoding="utf-8") as handle:
            cfg = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, None, f"could not read/parse {config_path}: {exc}"
    paths = cfg.get("paths") or {}
    install_dir = install_dir or paths.get("install_dir")
    mods_dir = mods_dir or paths.get("mods_dir")
    if not install_dir or not mods_dir:
        return None, None, (
            f"{config_path} has no paths.install_dir and/or paths.mods_dir. "
            f"Found: {sorted(paths.keys())}.")
    return install_dir, mods_dir, None


def collect_install_files(install_dir):
    """Every interesting definition file under the install, as {path: bytes}.

    Filtered by CONTENT, not by filename: the base game ships 503 placeable
    XMLs and only 74 carry a <production>. A name-based filter would need a list
    that goes stale with every game patch.
    """
    kept = {}
    for _label, parts in INSTALL_SUBTREES:
        root = os.path.join(install_dir, *parts)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if not name.lower().endswith(".xml"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, "rb") as handle:
                        blob = handle.read()
                except OSError:
                    # Unreadable single file: recorded, never silently skipped.
                    kept[path] = None
                    continue
                if any(token in blob for token in INTERESTING):
                    kept[path] = blob
    maps_bales = os.path.join(install_dir, *INSTALL_MAPS_BALES)
    if os.path.isfile(maps_bales):
        try:
            with open(maps_bales, "rb") as handle:
                kept[maps_bales] = handle.read()
        except OSError:
            kept[maps_bales] = None
    return kept


def collect_mod_files(mods_dir):
    """Every interesting definition file inside every mod zip, as {path: bytes}.

    The path form is `<zip>!<member>` -- a FULL path, never a basename, so the
    two maps_bales.xml files cannot collide (sec. 6.5).
    """
    kept = {}
    if not os.path.isdir(mods_dir):
        return kept
    for name in sorted(os.listdir(mods_dir)):
        if not name.lower().endswith(".zip"):
            continue
        zip_path = os.path.join(mods_dir, name)
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for member in archive.namelist():
                    if not member.lower().endswith(".xml"):
                        continue
                    try:
                        blob = archive.read(member)
                    except (KeyError, OSError, zipfile.BadZipFile):
                        continue
                    if any(token in blob for token in INTERESTING):
                        kept["%s!%s" % (zip_path, member)] = blob
        except (zipfile.BadZipFile, OSError):
            # A mod zip that will not open is reported by the caller as a
            # partial read, never skipped in silence.
            kept["%s!<unopenable>" % zip_path] = None
    return kept


def root_provenance(label, root_path, files):
    """One sources[] record per ROOT, not per file. See the module docstring for
    why this deviates from sec. 2.1's shape and what is and is not lost."""
    lines = sorted(
        "%s\0%s" % (path, hashlib.sha256(blob).hexdigest())
        for path, blob in files.items() if blob is not None)
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {
        "path": root_path,
        "kind": label,
        "file_count": len(lines),
        "unreadable_count": sum(1 for b in files.values() if b is None),
        "sha256": digest,
    }


def source_set_hash(sources):
    """sec. 2.1: one comparable scalar over the whole source set."""
    lines = sorted("%s\0%s" % (s["path"], s["sha256"]) for s in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def parse_all(files, malformed):
    """Parse every definition file ONCE, returning {path: (blob, root_or_None)}.

    ⚠ PARSED ONCE, NOT ONCE PER READER, AND THAT IS A CORRECTNESS FIX AS WELL AS
    A SPEED ONE. The six readers below each used to call a per-file parse, so a
    single malformed file was appended to `malformed` once for every reader that
    reached it -- and read_recipes runs TWICE (greenhouse and non-greenhouse), so
    one broken file reported as two. A count that inflates with the number of
    consumers is not a count of anything.

    It also parsed 305 files up to six times each. Parsing once is simply what
    the readers needed all along.
    """
    parsed = {}
    for path in sorted(files):
        blob = files[path]
        if blob is None:
            parsed[path] = (None, None)
            continue
        try:
            parsed[path] = (blob, ET.fromstring(blob))
        except ET.ParseError as exc:
            malformed.append("%s: %s" % (path, exc))
            parsed[path] = (blob, None)
    return parsed


def read_recipes(parsed, want_greenhouse):
    """<production> rows, from either the base or the mod tree.

    want_greenhouse selects which files contribute: b8's greenhouses carry BOTH
    a <greenhouse> block and a normal <productionPoint>, and the inventory is
    explicit that the economics live in the latter. Splitting them by the
    presence of <greenhouse> keeps b1/b2 and b8 from double-counting the same
    <production> element.
    """
    rows = []
    for path, (blob, root) in sorted(parsed.items()):
        if blob is None or root is None:
            continue
        if (b"<greenhouse" in blob) != want_greenhouse:
            continue
        for production in root.iter("production"):
            inputs, outputs = [], []
            for holder, sink in (("inputs", inputs), ("outputs", outputs)):
                for group in production.findall(holder):
                    for entry in group:
                        sink.append(build_row([
                            ("fill_type", opt(entry.attrib, "fillType")),
                            ("amount", opt(entry.attrib, "amount")),
                        ]))
            rows.append(build_row([
                ("source_path", path),
                ("production_id", opt(production.attrib, "id")),
                ("name", opt(production.attrib, "name")),
                ("cycles_per_hour", opt(production.attrib, "cyclesPerHour")),
                ("costs_per_active_hour",
                 opt(production.attrib, "costsPerActiveHour")),
                ("inputs", inputs),
                ("outputs", outputs),
                ("input_count", len(inputs)),
                ("output_count", len(outputs)),
            ]))
    return rows


def read_capacities(parsed):
    """b7 -- <storage><capacity fillType capacity>. THE CEILING."""
    rows = []
    for path, (blob, root) in sorted(parsed.items()):
        if blob is None or root is None or b"<capacity " not in blob:
            continue
        for storage in root.iter("storage"):
            for capacity in storage.findall("capacity"):
                rows.append(build_row([
                    ("source_path", path),
                    ("fill_type", opt(capacity.attrib, "fillType")),
                    ("capacity", opt(capacity.attrib, "capacity")),
                    ("is_extension", opt(storage.attrib, "isExtension")),
                ]))
    return rows


def read_greenhouse_plants(parsed):
    """b8's plant SLOTS. Never a growth stage -- c7 measured that as runtime
    state with zero savegame support, and no definition file carries it either."""
    rows = []
    for path, (blob, root) in sorted(parsed.items()):
        if blob is None or root is None or b"<greenhouse" not in blob:
            continue
        for greenhouse in root.iter("greenhouse"):
            for plants in greenhouse.findall("plants"):
                for plant in plants.findall("plant"):
                    rows.append(build_row([
                        ("source_path", path),
                        ("fill_type", opt(plant.attrib, "fillType")),
                        ("plant_xml", opt(plant.attrib, "xmlFilename")),
                    ]))
    return rows


def read_bale_definitions(parsed):
    """b20 -- per-fillType capacity/mass/wrappability, plus fermentation."""
    rows = []
    for path, (blob, root) in sorted(parsed.items()):
        if blob is None or root is None or root.tag != "bale":
            continue
        fermenting = None
        for element in root.iter("fermenting"):
            fermenting = build_row([
                ("output_fill_type", opt(element.attrib, "outputFillType")),
                ("requires_wrapping", opt(element.attrib, "requiresWrapping")),
                ("time", opt(element.attrib, "time")),
            ])
            break
        for fill_type in root.iter("fillType"):
            rows.append(build_row([
                ("source_path", path),
                ("fill_type", opt(fill_type.attrib, "name")),
                ("capacity", opt(fill_type.attrib, "capacity")),
                ("mass", opt(fill_type.attrib, "mass")),
                ("supports_wrapping", opt(fill_type.attrib, "supportsWrapping")),
                ("fermenting", fermenting if fermenting is not None else _ABSENT),
            ]))
    return rows


def read_map_bale_set(parsed):
    """b21 -- every maps_bales.xml, KEYED BY FULL PATH.

    Two files share the basename `maps_bales.xml` (install and map mod), so
    merging on basename would silently fuse two different bale sets. Rows carry
    source_path and are never merged.
    """
    rows = []
    for path, (blob, root) in sorted(parsed.items()):
        if os.path.basename(path.split("!")[-1]) != "maps_bales.xml":
            continue
        if blob is None or root is None:
            continue
        for bale in root.iter("bale"):
            rows.append(build_row([
                ("source_path", path),
                ("filename", opt(bale.attrib, "filename")),
                # MEASURED: present on 1 of 11 base bales and 2 of 19 mod bales.
                # The inventory's "19 <bale filename isAvailable> entries" reads
                # as though it is on all 19. Absent means absent, not "false".
                ("is_available", opt(bale.attrib, "isAvailable")),
            ]))
    return rows


def read_pallet_definitions(parsed):
    """b24 -- pallets are VEHICLES, not placeables, and one model may carry
    several fillTypes (`fillTypes="FLOUR RICEFLOUR"`)."""
    rows = []
    for path, (blob, root) in sorted(parsed.items()):
        if blob is None or root is None or b'type="pallet"' not in blob:
            continue
        for unit in root.iter("fillUnit"):
            raw_types = unit.attrib.get("fillTypes")
            if raw_types is None:
                continue
            rows.append(build_row([
                ("source_path", path),
                # Split, and the LIST is emitted rather than the raw string --
                # one model carrying several fillTypes is the documented shape,
                # and a consumer matching the whole string would miss the second.
                ("fill_types", raw_types.split()),
                ("fill_type_count", len(raw_types.split())),
                ("capacity", opt(unit.attrib, "capacity")),
            ]))
    return rows


def roll_up(sections):
    """Top-level status/reason -- sec. 6.3.3, rev 4. TOTAL, ORDERED, FIRST MATCH WINS.

        1. ANY section unavailable or partial -> "partial"
        2. EVERY section unknown_by_design    -> "unknown_by_design"
        3. otherwise (>=1 ok, none failed)    -> "ok"

    COPIED, NOT IMPORTED -- extracting it to xml_utils.py would breach
    TECH-DEBT-023. Guarded by this suite's own exhaustive truth table.

    Rule 1 outranks rule 2 deliberately: unknown_by_design is a positive claim,
    and a failed section means we do not know. The ORDER of rules 1 and 2 is
    unobservable (their conditions are disjoint -- finding M9) and no test here
    claims otherwise; what is measured is that deleting either rule, or dropping
    the empty-sections guard, turns this suite red.
    """
    degraded = sorted(name for name, s in sections.items()
                      if s["status"] in ("unavailable", "partial"))
    if degraded:
        return "partial", "section(s) not fully read: " + "; ".join(
            "%s (%s): %s" % (n, sections[n]["status"], sections[n]["reason"])
            for n in degraded)
    if sections and all(s["status"] == "unknown_by_design"
                        for s in sections.values()):
        return ("unknown_by_design",
                "no data of any kind on this farm for this domain")
    return "ok", None


def section(rows, status, reason, capability_ids, shape, typing, guarantees,
            identity_fields, source_elements):
    return {
        "status": status,
        "reason": reason,
        "shape": shape,
        "capability_ids": list(capability_ids),
        "typing": dict(typing),
        "typing_guarantee": dict(guarantees),
        "identity_fields": list(identity_fields),
        "empty_means": "not_applicable",
        # Every section here reads a PRESENT, enumerated tree. Nothing is
        # inferred from an absent container, so sec. 6.3.1 rule 2 never fires
        # and no licence is owed (sec. 6.3.1 rule 4).
        "absence_guarantee": None,
        "source_elements": list(source_elements),
        # BUG-014's one blocked element is farms.xml's fieldPurchase (DEC-057 ⑧
        # dropped the farmland raster). This domain reads neither -- it does not
        # open the savegame at all.
        "blocked_by": None,
        "count": len(rows),
        "data": rows,
    }


# EVERY VALUE HERE IS raw, AND THAT IS A DECISION WITH A REASON.
#
# sec. 6.5 rule 2 requires a citation naming the schema element that guarantees a
# coercion is lossless. These are DEFINITION files, and the install ships no XSD
# for them -- the 88 schemas under shared/xml/schema cover savegame and a few
# config shapes, not data/placeables/*.xml. So no citation can be made, and
# rule 1's default stands: everything ships as the exact source text.
#
# This is the same shape as the `bool` finding one domain over: where the
# guarantee does not exist, the rule's own fallback is raw, and inventing a
# citation to justify a coercion would be the laundering sec. 6.3.2 warns about.
# `capacity`, `amount` and `cyclesPerHour` are therefore STRINGS. A consumer that
# needs arithmetic converts them and owns that conversion.
_RAW_ONLY = "no XSD covers data/placeables definition files, so sec. 6.5 rule 1's raw default stands"


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        emit({"usage": USAGE, "domain": DOMAIN, "capability_ids": CAPABILITY_IDS})
        return

    farm_id, config, install_dir, mods_dir, arg_err = parse_args(sys.argv)
    if arg_err:
        fail(arg_err, calibration_needed=False)

    install_dir, mods_dir, path_err = load_paths(config, install_dir, mods_dir)
    if path_err:
        fail(path_err, calibration_needed=False)
    if not os.path.isdir(install_dir):
        fail(f"install_dir does not exist: {install_dir!r}. Definitions cannot "
             "be read, and reporting an empty recipe graph would be worse than "
             "failing.", calibration_needed=False)

    install_files = collect_install_files(install_dir)
    mod_files = collect_mod_files(mods_dir)
    if not install_files:
        fail(f"no definition files found under {install_dir!r}. Expected XML "
             "under data/placeables, data/objects/pallets and data/objects/bales. "
             "An empty result here means the install layout changed, not that "
             "the game has no productions.", calibration_needed=True)

    all_files = dict(install_files)
    all_files.update(mod_files)
    malformed = []

    provenance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "sources": [
            root_provenance("install", install_dir, install_files),
            root_provenance("mods", mods_dir, mod_files),
        ],
    }
    provenance["source_set_hash"] = source_set_hash(provenance["sources"])

    parsed = parse_all(all_files, malformed)
    recipes = read_recipes(parsed, want_greenhouse=False)
    greenhouse_recipes = read_recipes(parsed, want_greenhouse=True)
    plants = read_greenhouse_plants(parsed)
    capacities = read_capacities(parsed)
    bale_defs = read_bale_definitions(parsed)
    map_bales = read_map_bale_set(parsed)
    pallets = read_pallet_definitions(parsed)

    unreadable = sum(1 for b in all_files.values() if b is None)
    degraded_note = ""
    if malformed or unreadable:
        degraded_note = (
            " PARTIAL: %d file(s) would not parse and %d could not be read; "
            "the counts above are therefore a floor, not a total."
            % (len(malformed), unreadable))

    def status_for(rows):
        """A section that found nothing where the trees are populated is
        `unavailable`, not a confident 'this game has none' -- the definition
        trees are present and enumerable, so an empty result means the layout
        moved, which is something we could not find out rather than a fact about
        the game."""
        if malformed or unreadable:
            return "partial"
        return "ok" if rows else "unavailable"

    sections = {}

    sections["production_recipes"] = section(
        recipes, status_for(recipes),
        ("%d production recipe(s) across the base game and every installed mod, "
         "keyed by full source path. Greenhouse recipes are NOT here -- they "
         "carry their own <greenhouse> block and are reported separately, so the "
         "same <production> element is never counted twice.%s"
         % (len(recipes), degraded_note)) if recipes else
        ("no <production> element found under the install or any mod. The "
         "definition trees were enumerated and are present, so this is a layout "
         "change we could not interpret, not a game without productions."),
        ["b1", "b2"], "recipe_graph",
        {"source_path": "raw", "production_id": "raw", "name": "raw",
         "cycles_per_hour": "raw", "costs_per_active_hour": "raw",
         "inputs": "raw", "outputs": "raw", "input_count": "int",
         "output_count": "int", "absent_attributes": "raw"},
        {"input_count": "a cardinality this script computes over <inputs> "
                        "children, not a source attribute",
         "output_count": "a cardinality this script computes over <outputs> "
                         "children, not a source attribute"},
        ["source_path", "production_id"],
        ["install/data/placeables/**.xml:placeable/productionPoint/production",
         "mods/*.zip!**.xml:placeable/productionPoint/production"])

    sections["storage_capacities"] = section(
        capacities, status_for(capacities),
        ("%d per-fillType capacity ceiling(s). THIS IS THE HALF THE SAVEGAME "
         "DOES NOT HAVE: read_productions.py's storage_fill_levels reports what "
         "a production storage HOLDS and explicitly refuses to imply a ratio, "
         "because the ceiling lives here. Neither script computes the ratio; the "
         "join belongs to whatever consumes both.%s"
         % (len(capacities), degraded_note)) if capacities else
        ("no <storage><capacity> found. Without this no 'silo full' verdict is "
         "computable from any of this set's scripts."),
        ["b7"], "keyed_records",
        {"source_path": "raw", "fill_type": "raw", "capacity": "raw",
         "is_extension": "raw", "absent_attributes": "raw"},
        {}, ["source_path", "fill_type"],
        ["install/data/placeables/**.xml:placeable/productionPoint/storage/capacity",
         "mods/*.zip!**.xml:placeable/productionPoint/storage/capacity"])

    sections["greenhouse_recipes"] = section(
        greenhouse_recipes + plants, status_for(greenhouse_recipes + plants),
        ("%d greenhouse recipe(s) and %d plant slot(s). A greenhouse carries TWO "
         "blocks -- a <greenhouse><plants> block (the slots) and a normal "
         "<productionPoint> (the economics) -- and both are reported. PLANT "
         "GROWTH STAGE IS NOT AND CANNOT BE HERE: c7 measures zero greenhouse "
         "references in any savegame XSD, and no definition file carries runtime "
         "state either.%s" % (len(greenhouse_recipes), len(plants), degraded_note))
        if (greenhouse_recipes or plants) else
        "no placeable declaring a <greenhouse> block was found under the install.",
        ["b8"], "recipe_graph",
        {"source_path": "raw", "production_id": "raw", "name": "raw",
         "cycles_per_hour": "raw", "costs_per_active_hour": "raw",
         "inputs": "raw", "outputs": "raw", "input_count": "int",
         "output_count": "int", "fill_type": "raw", "plant_xml": "raw",
         "absent_attributes": "raw"},
        {"input_count": "a cardinality this script computes over <inputs> "
                        "children, not a source attribute",
         "output_count": "a cardinality this script computes over <outputs> "
                         "children, not a source attribute"},
        ["source_path", "production_id"],
        ["install/data/placeables/**.xml:placeable/greenhouse/plants/plant",
         "install/data/placeables/**.xml:placeable/productionPoint/production"])

    sections["bale_definitions"] = section(
        bale_defs, status_for(bale_defs),
        ("%d bale fillType definition(s) -- capacity, mass, wrappability, and "
         "the <fermenting> block where one exists.%s" % (len(bale_defs), degraded_note))
        if bale_defs else
        "no <bale> definition found under data/objects/bales.",
        ["b20"], "keyed_records",
        {"source_path": "raw", "fill_type": "raw", "capacity": "raw",
         "mass": "raw", "supports_wrapping": "raw", "fermenting": "raw",
         "absent_attributes": "raw"},
        {}, ["source_path", "fill_type"],
        ["install/data/objects/bales/**.xml:bale/fillType"])

    sections["map_bale_set"] = section(
        map_bales, status_for(map_bales),
        ("%d <bale> entries across every maps_bales.xml found, KEYED BY FULL "
         "PATH. Two files share that basename -- the install's and the map "
         "mod's -- so rows are never merged across paths (sec. 6.5). Measured on "
         "this machine: 11 in the install, 19 in the mod, symmetric difference "
         "8, and `only in base` is ZERO, so the mod set is a strict SUPERSET "
         "rather than the 'disjoint values / 87 diffs' sec. 6.5 describes.%s"
         % (len(map_bales), degraded_note)) if map_bales else
        "no maps_bales.xml found in the install or any mod.",
        ["b21"], "record_list",
        {"source_path": "raw", "filename": "raw", "is_available": "raw",
         "absent_attributes": "raw"},
        {}, ["source_path", "filename"],
        ["install/data/maps/maps_bales.xml:map/bales/bale",
         "mods/*.zip!**/maps_bales.xml:map/bales/bale"])

    sections["pallet_definitions"] = section(
        pallets, status_for(pallets),
        ("%d pallet fillUnit definition(s). Pallets are VEHICLES, not "
         "placeables, and one model may carry several fillTypes -- fill_types is "
         "a LIST, because a consumer matching the raw string would miss the "
         "second.%s" % (len(pallets), degraded_note)) if pallets else
        "no vehicle definition with type=\"pallet\" found under data/objects/pallets.",
        ["b24"], "keyed_records",
        {"source_path": "raw", "fill_types": "raw", "fill_type_count": "int",
         "capacity": "raw", "absent_attributes": "raw"},
        {"fill_type_count": "a cardinality this script computes by splitting "
                            "@fillTypes on whitespace, not a source attribute"},
        ["source_path"],
        ["install/data/objects/pallets/**.xml:vehicle/fillUnit"])

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
        # Definitions are identical for every farm. Said out loud so nobody reads
        # farm_id above as evidence this output was filtered.
        "farm_id_is_not_a_filter": (
            "definitions are identical for every farm on a save; farm_id is "
            "recorded for envelope consistency and filters nothing"),
    }
    if malformed:
        envelope["malformed_files"] = malformed[:20]
        envelope["malformed_file_count"] = len(malformed)
    emit(envelope)


if __name__ == "__main__":
    main()
