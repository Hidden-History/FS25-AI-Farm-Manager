"""
DOMAIN SCRIPT (b3, b4, b5, b6, b9) -- production points, emitted in the sec. 6.2
domain envelope.

Usage: python3 read_productions.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

Built against architecture-farm-manager-cached-state.md rev 4. Follows the
template read_livestock.py established: the sec. 6.2 envelope, sec. 6.3.1's
absence rule, sec. 6.3.3's roll-up and sec. 6.5's typing rule.

Reads ONE file, read-only: placeables.xml. Nothing here writes to the savegame,
ever. The only writes this process performs are to stdout.

    b3  <productionPoint><production id= isEnabled=>
    b4  <productionPoint productionCostsToClaim=>
    b5  <productionPoint><autoDeliverFillType>/<directSellFillType>
    b6  <productionPoint palletSpawnCooldown=>
    b9  <FS25_GreenhouseAutomaticWatering><AutomaticWateringSpecialization AutoWatering=>

WHAT THIS SCRIPT DOES NOT DO, AND WHY THAT IS NOT A GAP
-------------------------------------------------------
The `production` set also covers the RECIPE GRAPH (b1, b2), storage CEILINGS
(b7), greenhouse recipes (b8) and bale/pallet definitions (b20, b21, b24). None
of those live in the savegame: they are definition data in the game install and
the map mod. This script reads the savegame only. The distinction is load-
bearing for b7 -- the savegame gives a fill LEVEL, only the definition gives the
capacity that would make "silo full" computable -- so `storage_fill_levels`
below reports the level and says plainly that it carries no ceiling. Reporting a
level as if it were a ratio is the kind of quiet over-claim this envelope exists
to prevent.

TWO PRODUCTION CAPABILITIES ARE MEASURED NOT AVAILABLE, AND ARE NOT EMITTED
---------------------------------------------------------------------------
Not omitted silently -- stated here with the measurement, per the inventory's
bucket (c):

    c5  production cycle progress / partial-cycle position
        grep -c -i "progress\\|cycle\\|elapsed" savegame_placeables.xsd  ->  0
        The saved <production> element carries ONLY id and isEnabled. Cycle
        position is runtime state and is never written to the savegame.

    c7  greenhouse plant growth stage as saved state
        grep -c -i greenhouse savegame_placeables.xsd  ->  0
        grep -ril greenhouse across all savegame_*.xsd / *_savegame.xsd -> 0 files

Both re-measured on this install (88 XSDs) rather than inherited from the
inventory. A section for either would be a section that can never carry data,
which is absence dressed as a capability.

OWNERSHIP FILTERING IS NOT OPTIONAL
-----------------------------------
Measured on the live save: 39 <productionPoint> elements exist, and only SIXTEEN
belong to the player. Ten are farmId=0 and thirteen are farmId=15 -- map
furniture, the map's own factories. A reader that skips the farmId filter
describes the MAP, not the FARM, and reports a 2.4x overcount. This is the same
trap that bit b10 at 22-of-25 animal husbandries; it is not a livestock quirk,
it is how this map is built. Every placeable considered here is filtered on the
<placeable> element's own farmId attribute.

TYPING (sec. 6.5) -- AND THE `bool` BRANCH IS UNREACHABLE, MEASURED
--------------------------------------------------------------------
sec. 6.5's hazard table says a boolean-as-string is coerced to `bool` "only with
an XSD xs:boolean citation; else raw", and it names `isEnabled` and
`AutoWatering` as its two worked examples. Both are this script's fields.

THAT CITATION CANNOT BE MADE, HERE OR ANYWHERE. Measured across all 88 XSDs in
this install:

    grep -l 'type="xs:boolean"' shared/xml/schema/*.xsd | wc -l   ->  0
    g_bool, in every XSD that declares it:
        <xs:restriction base="xs:string"><xs:pattern value="true|false"/>

g_bool is a restriction of xs:string, NOT of xs:boolean. So no FS25 savegame
field can satisfy the rule's condition, and the `"bool"` member of sec. 6.2's
typing vocabulary is unreachable in this codebase. `isEnabled` and `AutoWatering`
therefore ship RAW -- which is exactly what the hazard table's own fallback
requires, so this script is compliant, not excepted.

No test in the accompanying suite asserts that a bool coercion goes red: a test
written to satisfy a clause that cannot be satisfied cannot fail, and a test that
cannot fail is worse than no test. The measurement above is the honest
replacement, and it is asserted directly -- test_g_bool_is_not_xs_boolean.

AutoWatering has a second, independent reason to stay raw: it is a MOD element
(FS25_GreenhouseAutomaticWatering) and the base XSD does not declare it at all
(grep -c -> 0). There is no schema to cite even in principle.

ABSENCE OF AN OPTIONAL ATTRIBUTE IS NOT ZERO, AND THE XSD SETTLES IT
---------------------------------------------------------------------
b4's productionCostsToClaim is absent on 17 of the 39 production points, and b6's
palletSpawnCooldown is absent on ALL 39. Emitting 0.0 for an absent attribute
would be substituting a default, which sec. 6.5 rule 3 forbids and DEC-001 exists
to prevent -- "nothing to claim" and "the file does not say" are different facts.

The XSD is not silent on this, and the contrast is the evidence:

    <xs:attribute name="fillLevel"              type="g_float" default="0">
    <xs:attribute name="productionCostsToClaim" type="g_float">          <- none
    <xs:attribute name="palletSpawnCooldown"    type="g_int">            <- none

The schema author gave storage/@fillLevel an explicit default of 0 and gave
neither of these one. An absent fillLevel IS zero, by citation. An absent
productionCostsToClaim is NOT, by the same citation read the other way. So rows
are emitted only for production points that actually carry the attribute, and the
count of those that do not is reported in the section's reason rather than folded
into the data.

Where NO production point carries the attribute -- b6's state on this save -- the
section reports `unavailable`, not `unknown_by_design`: sec. 6.3.1 rule 1 makes
`unavailable` the default for an unlicensed absence, and claiming
"no pallet spawner is on cooldown" would be a positive assertion about the farm
that nothing licenses. Under sec. 6.3.3 rule 1 that makes the whole domain
`partial` on this save, which is the honest reading: part of it genuinely could
not be determined.

Output contract:
    - Could-not-run -- bad args, unreadable placeables.xml, unknown farm_id --
      emits a top-level {"error": ...} and exits 1 (sec. 6.3, DEC-001). Never [],
      never {}, never None, never a coerced guess.
    - The script ran -- the envelope is emitted with all six sections always
      present. No section is ever suppressed, on any farm, ever.
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit, resolve_game_xml, MODDIR_RE
from read_store_prices import load_paths, extract_store_item

SCHEMA_VERSION = 1
GENERATOR = "read_productions.py"
GENERATOR_VERSION = "1.0.0"
USAGE = (
    "read_productions.py <savegame_dir> [--farm-id N] "
    "[--config PATH] [--install-dir DIR] [--mods-dir DIR]")

DOMAIN = "productions"
SET = "production"
CAPABILITY_IDS = ["b3", "b4", "b5", "b6", "b9"]

# sec. 6.5 rule 2: every coerced field carries its own citation, per field. A
# blanket citation cannot be checked against the attribute it claims to cover.
_G_FLOAT = "g_float -> xs:restriction base=xs:float (savegame_placeables.xsd:30-33)"
_G_INT = "g_int -> xs:restriction base=xs:integer (savegame_placeables.xsd:50-53)"

# The mod element b9 reads is not in the base schema at all, so there is nothing
# to cite and rule 1's default stands. Recorded as a constant so the suite can
# assert the section carries no typing_guarantee rather than trusting prose.
B9_MOD_ELEMENT = "FS25_GreenhouseAutomaticWatering"


def fail(message, **extra):
    """Top-level could-not-run: structured error, exit 1 (sec. 6.3, DEC-001).

    Every message this script can emit is deliberately distinct. Byte-identical
    duplicate error emissions are what defeated a mutation harness in
    TECH-DEBT-021 item 1 and produced two false 'no teeth' verdicts.
    """
    payload = {"error": message}
    payload.update(extra)
    emit(payload)
    sys.exit(1)


def parse_args(argv):
    """Pull --farm-id N (or --farm-id=N) and the store-name resolver's
    --config/--install-dir/--mods-dir out of argv; default farm_id=1, all
    three paths None (best-effort name resolution -- see resolve_store_name).

    Returns (farm_id, config, install_dir, mods_dir, error_or_None).

    BOTH --farm-id SPELLINGS, AND NOTHING SWALLOWED -- the H3 defect
    read_livestock.py carries a note on, kept exactly as it was when this
    parser only knew --farm-id. A parser that understands only the
    space-separated form and drops unrecognised arguments answers
    `--farm-id=15` with farm 1 and exits 0: a confidently reported WRONG FARM.
    In this domain that would report 16 player factories as though they were
    someone else's, or 13 of the map's as though they were the player's. An
    unrecognised argument is an error -- including a typo in one of the three
    new path flags.
    """
    farm_id = 1
    config = install_dir = mods_dir = None
    args = argv[2:]  # argv[0] = script, argv[1] = savegame_dir (already consumed)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--farm-id":
            if i + 1 >= len(args):
                return None, None, None, None, (
                    f"usage: {USAGE} -- --farm-id given with no value")
            raw = args[i + 1]
            i += 2
            try:
                farm_id = int(raw)
            except ValueError:
                return None, None, None, None, (
                    f"--farm-id must be an integer, got {raw!r}")
        elif arg.startswith("--farm-id="):
            raw = arg.split("=", 1)[1]
            i += 1
            try:
                farm_id = int(raw)
            except ValueError:
                return None, None, None, None, (
                    f"--farm-id must be an integer, got {raw!r}")
        elif arg in ("--config", "--install-dir", "--mods-dir"):
            if i + 1 >= len(args):
                return None, None, None, None, (
                    f"usage: {USAGE} -- {arg} given with no value")
            val = args[i + 1]
            if arg == "--config":
                config = val
            elif arg == "--install-dir":
                install_dir = val
            else:
                mods_dir = val
            i += 2
        else:
            return None, None, None, None, (
                f"unrecognised argument {arg!r} -- refusing to ignore it and "
                f"report the default farm. usage: {USAGE}")
    return farm_id, config, install_dir, mods_dir, None


def file_provenance(path):
    """sec. 2.1 source record. Hashes only the file this domain actually reads."""
    stat = os.stat(path)
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return {
        "path": path,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": digest,
    }


def source_set_hash(sources):
    """sec. 2.1: sha256 over the sorted `path\\0sha256` lines. One comparable
    scalar per domain, and the thing that actually decides currency."""
    lines = sorted("%s\0%s" % (s["path"], s["sha256"]) for s in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def roll_up(sections):
    """Top-level status/reason -- sec. 6.3.3, rev 4. TOTAL, ORDERED, FIRST MATCH WINS.

        1. ANY section unavailable or partial -> "partial"
        2. EVERY section unknown_by_design    -> "unknown_by_design"
        3. otherwise (>=1 ok, none failed)    -> "ok"

    (Rule 0 -- the script could not run at all -> {"error": ...} + exit 1 -- is
    handled by fail() before any section is built, so it cannot reach here.)

    COPIED FROM read_livestock.py DELIBERATELY, NOT IMPORTED. Extracting this
    into xml_utils.py would breach TECH-DEBT-023; the duplication is by design
    and the b10 suite's exhaustive truth table is the guard on that copy, as this
    suite's is on this one.

    RULE 1 OUTRANKS RULE 2 DELIBERATELY. A domain that is PARTLY unreadable must
    never report the confident unknown_by_design: that status is a positive claim
    about the farm, and a failed section means we do not know. sec. 6.3.3 -- the
    status that claims more never wins a tie.

    ⚠ THE ORDER OF RULES 1 AND 2 IS UNOBSERVABLE, and no test here claims
    otherwise. The conditions are disjoint: rule 2 fires only when EVERY section
    is unknown_by_design, which means none is unavailable or partial, which is
    rule 1's condition failing. Swapping the branches is a semantic no-op. This
    is finding M9 from the livestock lane, and the honest guard is the exhaustive
    truth table in the accompanying suite -- deleting rule 1, deleting rule 2, or
    dropping the empty-sections guard each turn it red, and those ARE measured.

    ⚠ THIS DOMAIN EXERCISES RULE 1 FOR REAL. On the live save
    pallet_spawn_cooldown is `unavailable` while other sections are `ok`, so the
    top level is `partial`. Both wave-1 lanes implemented a rule that would have
    answered `ok` here.
    """
    degraded = sorted(name for name, s in sections.items()
                      if s["status"] in ("unavailable", "partial"))
    if degraded:
        return "partial", "section(s) not fully read: " + "; ".join(
            "%s (%s): %s" % (n, sections[n]["status"], sections[n]["reason"])
            for n in degraded)

    # `sections and` guards the vacuous case: all() over an empty dict is True,
    # which would turn a domain that emitted NO sections into the confident claim
    # "this farm has none". A domain with no sections is a bug (sec. 6.4), never a
    # positive fact.
    if sections and all(s["status"] == "unknown_by_design" for s in sections.values()):
        return ("unknown_by_design",
                "no data of any kind on this farm for this domain")

    return "ok", None


def resolve_mod_l10n_text(mods_dir, mod_name, bare_key):
    """The l10n hop (D4): a mod's modDesc.xml <l10n> block, INLINE or via an
    external translations/*_en.xml named by filenamePrefix=.

    Verified against this install's own mods (2026-09-15): FS25_hydroGreenhouse
    and the FS25_placeable*ByStevie mods define l10n INLINE --
    <l10n><text name="KEY"><en>Value</en></text></l10n> directly in modDesc.xml.
    FS25_Montana_4X instead declares <l10n filenamePrefix="translations/l10n"/>
    and keeps the text in translations/l10n_en.xml, shaped
    <l10n><texts><text name="KEY" text="Value"/></texts></l10n> -- a DIFFERENT
    element shape from the inline case (attribute, not an <en> child). Both are
    real, both are in this farm's own save, and a resolver that only knows one
    of them silently fails on the other's placeables.

    Returns (text_or_None, source, reason_or_None). `source` is "l10n_inline"
    or "l10n_external" and is set even on failure, so a caller can report which
    hop was attempted. Never raises: a zip that will not open, a modDesc.xml
    that will not parse, or a key that is genuinely absent are all reasoned
    refusals, never a crash and never a guess (DEC-001).
    """
    if not mods_dir:
        return None, "l10n_inline", (
            "no mods directory configured -- pass --mods-dir/--install-dir or "
            "set sanctum/config.json's paths block")
    zip_path = os.path.join(mods_dir, mod_name + ".zip")
    try:
        with zipfile.ZipFile(zip_path) as z:
            try:
                desc_data = z.read("modDesc.xml")
            except KeyError:
                return None, "l10n_inline", f"{zip_path} has no modDesc.xml"
            try:
                desc_root = ET.fromstring(desc_data)
            except ET.ParseError as exc:
                return None, "l10n_inline", (
                    f"modDesc.xml in {zip_path} does not parse: {exc}")

            l10n = desc_root.find("l10n")
            if l10n is None:
                return None, "l10n_inline", (
                    f"{zip_path}'s modDesc.xml has no <l10n> element")

            for text_elem in l10n.findall("text"):
                if text_elem.attrib.get("name") != bare_key:
                    continue
                en = text_elem.find("en")
                if en is not None and en.text and en.text.strip():
                    return en.text.strip(), "l10n_inline", None
                return None, "l10n_inline", (
                    f"{zip_path}'s modDesc.xml <l10n> defines {bare_key!r} but "
                    "with no <en> translation")

            prefix = l10n.attrib.get("filenamePrefix")
            if not prefix:
                return None, "l10n_inline", (
                    f"{bare_key!r} is not defined in {zip_path}'s modDesc.xml "
                    "<l10n> block, and no filenamePrefix= names an external "
                    "translation file")

            ext_path = f"{prefix}_en.xml"
            try:
                ext_data = z.read(ext_path)
            except KeyError:
                return None, "l10n_external", (
                    f"{zip_path}'s modDesc.xml names filenamePrefix={prefix!r} "
                    f"but {ext_path!r} is not inside the zip")
            try:
                ext_root = ET.fromstring(ext_data)
            except ET.ParseError as exc:
                return None, "l10n_external", (
                    f"{ext_path} in {zip_path} does not parse: {exc}")

            texts = ext_root.find("texts")
            container = texts if texts is not None else ext_root
            for text_elem in container.findall("text"):
                if text_elem.attrib.get("name") != bare_key:
                    continue
                value = text_elem.attrib.get("text")
                if value and value.strip():
                    return value.strip(), "l10n_external", None
                return None, "l10n_external", (
                    f"{ext_path} in {zip_path} defines {bare_key!r} with an "
                    "empty text= attribute")
            return None, "l10n_external", (
                f"{bare_key!r} not found in {ext_path} inside {zip_path}")
    except (zipfile.BadZipFile, OSError) as exc:
        return None, "l10n_inline", f"could not read {zip_path}: {exc}"


def resolve_store_name(filename, install_dir, mods_dir):
    """The three-hop resolve (D4): savegame `filename` -> that file's own
    <storeData><name> -> if THAT is an $l10n_ key, the owning mod's modDesc.xml
    <l10n> block. NEVER returns a raw XML basename -- see the module docstring
    and PLAN-UI-FIXES-2026-09-15 item 11.

    Returns (name_or_None, source, reason_or_None). `source` is one of
    "literal", "l10n_inline", "l10n_external", "unresolved" -- always set, so
    a caller can tally outcomes without re-deriving them from the reason text.
    """
    if filename.startswith("$pdlcdir$"):
        return None, "unresolved", (
            f"{filename!r} is PDLC-packaged content -- .dlc files are encrypted "
            "and cannot be opened as a zip from disk (confirmed against this "
            "install's pdlc/ folder: zipfile raises BadZipFile on every one)")

    root, source_label, kind, err = resolve_game_xml(filename, install_dir, mods_dir)
    if root is None:
        return None, "unresolved", err

    item = extract_store_item(root, source_label)
    if item is None:
        return None, "unresolved", f"{source_label} has no <storeData>"

    if item["name_literal"]:
        return item["name_literal"], "literal", None

    key = item["name_l10n_key"]
    if not key:
        return None, "unresolved", (
            f"{source_label} <storeData><name> is present but empty")

    bare_key = key[len("$l10n_"):] if key.startswith("$l10n_") else key
    if kind != "mod":
        return None, "unresolved", (
            f"{source_label} names l10n key {key!r}; base-game l10n text is "
            "packed (dataS.gar/dataS2.gar) and not readable from this script "
            "(same limit read_store_prices.py's name_note documents)")

    mod_match = MODDIR_RE.match(filename)
    mod_name = mod_match.group(1)
    text, l10n_source, reason = resolve_mod_l10n_text(mods_dir, mod_name, bare_key)
    if text:
        return text, l10n_source, None
    return None, "unresolved", reason


def placeable_identity(placeable, farm_id, install_dir, mods_dir):
    """(uniqueId, display name, name_resolution_source, [reason]) for one
    placeable, or fail loud.

    ⚠ NAMED `name_resolution_source`, NOT `name_source` -- fix round 2 (F4).
    emit_productions_xml.py already owns a DIFFERENTLY-VALUED `name_source` /
    `nameSource` vocabulary ("literal"/"derived", the Lua GUI's own contract at
    build_points():857 and build_xml():1144/1156). No bug today -- that dict is
    built fresh and never reads this one -- but D3 (plan item 10, surfacing the
    reason fields) is the next natural edit to wire this row's fields through,
    and the moment it does, a same-named key silently colliding with an
    existing, differently-valued one is exactly this project's founding defect
    class. Renamed while nothing consumes it yet.

    uniqueId is the ONLY placeable-level identity savegame_placeables.xsd:1596
    declares (g_string, "Placeable's unique id"). Measured on the live save: all
    216 placeables carry it and there are zero duplicates.

    THE DISPLAY NAME USED TO BE THE FILENAME'S BASENAME (D4, PLAN-UI-FIXES
    item 11) -- a raw "hydroGreenhouse.xml" on screen, worse than the id-derived
    title emit_productions_xml.py already falls back to for preplaced objects
    with no filename at all. This resolves the REAL store name via
    resolve_store_name() instead. `filename=""` (preplaced map objects,
    measured: the canned-food factory is one) still short-circuits to
    "<unnamed>" with no resolution attempt -- there is nothing to resolve, and
    emit_productions_xml.py's existing id-derived fallback already handles it
    correctly. A resolution FAILURE (mod zip missing, l10n key absent, PDLC,
    base-game packed data, ...) ALSO becomes "<unnamed>", exactly the same
    sentinel, so the SAME proven fallback renders it -- but unlike the empty-
    filename case, the reason is carried alongside for a machine reader
    (DONE WHEN #1: readable name or a STATED reason, never a raw basename,
    never a bare `unknown`).
    """
    unique_id = placeable.attrib.get("uniqueId")
    if unique_id is None:
        fail(
            f"a <placeable> on farm {farm_id} carrying production data has no "
            "uniqueId attribute -- savegame_placeables.xsd:1596 declares it, and "
            "it is the only placeable identity the schema defines. Refusing to "
            "emit production rows that cannot be attributed to a specific "
            "placeable (sec. 7.3).",
            calibration_needed=True,
        )

    filename = placeable.attrib.get("filename", "") or ""
    if not filename:
        return unique_id, "<unnamed>", "no_filename", []

    name, source, reason = resolve_store_name(filename, install_dir, mods_dir)
    if name:
        return unique_id, name, source, []
    return unique_id, "<unnamed>", "unresolved", [reason]


def disambiguate_names(identities):
    """D5 -- greenhouse disambiguation, SEPARATE FROM D4 (PLAN-UI-FIXES item
    12). Two placeables of the same store item (this farm owns two
    FS25_hydroGreenhouse.xml greenhouses, measured) resolve through D4 to the
    IDENTICAL literal/l10n name, so D4 alone leaves two indistinguishable rows.

    `identities` is {key: [unique_id, name, source, reason_list]} (a LIST per
    entry so entries are mutated in place, matching placeable_identity's
    return shape). Every name that recurs gets a stable " #N" suffix, N
    assigned in the order `identities` iterates (Python dict order == the
    order placeables were visited, i.e. document order in placeables.xml) --
    so re-running against an unchanged save reproduces the same suffixes.

    "<unnamed>" is DELIBERATELY EXCLUDED even when it recurs: it is not a real
    name collision, it is several placeables that each failed resolution for
    their own reason, and emit_productions_xml.py's fallback only fires on the
    LITERAL string "<unnamed>" -- suffixing it to "<unnamed> #2" would silently
    turn off that fallback and print the sentinel itself on screen.
    """
    counts = {}
    for _, name, _, _ in identities.values():
        if name != "<unnamed>":
            counts[name] = counts.get(name, 0) + 1

    seen = {}
    for entry in identities.values():
        name = entry[1]
        if name == "<unnamed>" or counts[name] <= 1:
            continue
        seen[name] = seen.get(name, 0) + 1
        entry[1] = f"{name} #{seen[name]}"


def coerce(raw, kind, field, where):
    """Coerce one attribute, or fail loud. sec. 6.5 rule 3: a value that fails its
    declared coercion is an ERROR, never a fallback."""
    if kind == "float":
        try:
            value = float(raw)
        except ValueError:
            fail(
                f"<productionPoint {field}={raw!r}> on {where} is not a number, "
                "but the XSD declares it g_float. Refusing to coerce or drop it.",
                calibration_needed=True,
            )
        # NaN and +/-Infinity are floats in Python and are NOT JSON numbers --
        # json.dumps emits bare NaN/Infinity, which no strict JSON reader accepts.
        # read_farm_ledger.py hit this on the money ledger; the same guard belongs
        # on every g_float this codebase coerces.
        if value != value or value in (float("inf"), float("-inf")):
            fail(
                f"<productionPoint {field}={raw!r}> on {where} coerces to a "
                "non-finite float, which is not a JSON number. Refusing to emit it.",
                calibration_needed=True,
            )
        return value
    try:
        return int(raw)
    except ValueError:
        fail(
            f"<productionPoint {field}={raw!r}> on {where} is not an integer, "
            "but the XSD declares it g_int. Refusing to coerce or drop it.",
            calibration_needed=True,
        )


def main():
    # TECH-DEBT-021 item 3: ~15 parsers in this skill consume --help as the
    # savegame path and answer with a file-not-found error. Not repeated here.
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        emit({"usage": USAGE, "domain": DOMAIN, "capability_ids": CAPABILITY_IDS})
        return

    savegame_dir = arg_or_exit(USAGE)
    farm_id, cfg_arg, install_dir_arg, mods_dir_arg, arg_err = parse_args(sys.argv)
    if arg_err:
        fail(arg_err, calibration_needed=False)

    # Store-name resolution (D4/D5) is BEST-EFFORT, unlike every other input
    # this script requires: a farm with no readable install/mods directory
    # still has a real production report, just one where every point falls
    # back to "<unnamed>" with a reason instead of a resolved store name --
    # never a hard failure of the whole domain. load_paths' own error (no
    # config.json and no explicit dirs) is deliberately swallowed here; it
    # resurfaces per-placeable via resolve_store_name's own reason text.
    install_dir, mods_dir, _paths_err = load_paths(
        cfg_arg, install_dir_arg, mods_dir_arg)

    # ⛔ MEASURED 2026-09-15 (fix round 1, team-lead's open question 5): load_paths
    # REQUIRES install_dir AND mods_dir together to skip its own sanctum/config.json
    # lookup -- a caller passing ONLY --mods-dir (this domain's real orchestration
    # shape: refresh_state.py threads mods_dir alone through every sibling tab, the
    # SAME pattern collect_land/publish_farm_tab/publish_fields_tab already use, and
    # install_dir is never available at those call sites at all) gets BOTH values
    # silently discarded the moment that config file cannot be found relative to
    # the caller's cwd -- which is the ordinary case here, not an edge case.
    # Reproduced from cwd=/tmp: `--mods-dir <real mods dir>` alone resolved 0 of 27
    # names -- the exact defect this whole feature exists to fix, reintroduced by
    # a shared helper's stricter gate. install_dir is a genuine nice-to-have here
    # (it only changes a REFUSAL's wording for base-game placeables -- their l10n
    # is packed and unreadable either way, see resolve_store_name), never required
    # for a real name to appear, so an explicitly-passed single flag must not be
    # thrown away just because the other one is absent.
    if install_dir is None and mods_dir is None:
        if install_dir_arg or mods_dir_arg:
            install_dir, mods_dir = install_dir_arg, mods_dir_arg

    placeables_path = os.path.join(savegame_dir, "placeables.xml")
    root, generic = load_xml(placeables_path)
    if root is None:
        fail(
            f"could not read placeables.xml: {generic.get('error')}",
            calibration_needed=True,
        )

    provenance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "sources": [file_provenance(placeables_path)],
    }
    provenance["source_set_hash"] = source_set_hash(provenance["sources"])

    # --- Select by farmId, never by document order --------------------------
    placeables = list(root.iter("placeable"))
    if not placeables:
        fail(
            "placeables.xml parsed but contained no <placeable> elements -- "
            "schema may have changed.",
            calibration_needed=True,
            generic_dump=generic,
        )

    farms_seen = set()
    malformed_farm_ids = []
    owned = []
    for placeable in placeables:
        raw_id = placeable.attrib.get("farmId")
        if raw_id is None:
            continue
        try:
            fid = int(raw_id)
        except ValueError:
            malformed_farm_ids.append(raw_id)
            continue
        farms_seen.add(fid)
        if fid == farm_id:
            owned.append(placeable)

    # A farmId that will not parse is a SCHEMA SURPRISE, and every other schema
    # surprise in this file fails loud. Skipping it in silence is how a populated
    # factory disappears into a "this farm runs no productions" reading -- the C3
    # defect, in the domain next door. Dropped is not absent.
    if malformed_farm_ids:
        shown = ", ".join(repr(m) for m in sorted(set(malformed_farm_ids))[:5])
        fail(
            f"{len(malformed_farm_ids)} <placeable> element(s) carry a farmId "
            f"that is not an integer ({shown}). Ownership cannot be established "
            "for them, and skipping them in silence would let a running factory "
            "disappear into an empty production report. Refusing to drop them.",
            calibration_needed=True,
        )

    if not farms_seen:
        fail(
            "placeables.xml holds <placeable> elements but not one carries a "
            "farmId attribute -- ownership cannot be established, and reporting "
            "an unowned map's factories as this farm's production would be worse "
            "than failing.",
            calibration_needed=True,
        )

    if farm_id not in farms_seen:
        # Not a farm that runs no productions -- a farm that is not in this file
        # at all. Reporting farm_has_none here would convert a lookup miss into a
        # claim about a farm we never found.
        fail(
            f"farm_id {farm_id} owns no placeables in placeables.xml. "
            f"Available farm_ids: {sorted(farms_seen)}",
            calibration_needed=False,
        )

    # --- Walk the owned placeables once, collecting every section's rows ------
    #
    # EVERY SIBLING CONTAINER IS READ, NOT THE FIRST. savegame_placeables.xsd
    # declares productionPoint maxOccurs="1", but that is the SCHEMA's claim
    # about a well-formed file, not a guarantee about the bytes on disk -- a mod
    # can write what it likes, and this file already carries one mod's own
    # element (b9). find() would return the first and discard the rest in
    # silence, which is precisely the C2 defect: 42 animals dropped on the floor
    # and reported as "this farm owns none". findall() cannot under-report and
    # needs no assumption about the writer.
    production_points = 0
    # One row per OWNED <productionPoint> container, whether or not it declares
    # any <production> children. See the production_points section below.
    owned_points = []
    lines = []
    costs = []
    costs_absent = 0
    delivery = []
    cooldowns = []
    cooldowns_absent = 0
    storage_levels = []
    watering = []

    # --- D4/D5 name resolution: a PRE-PASS, not inline ------------------------
    #
    # D5 needs to see every owned placeable's resolved name BEFORE any of them
    # is used, to tell a genuine duplicate (two hydroGreenhouse.xml) from a
    # placeable that merely hasn't been visited yet -- which a single walk
    # cannot do, since `name` is consumed immediately for that placeable's b3
    # -- b9 rows in the SAME iteration it is computed. identities is keyed by
    # id(placeable) (the same Element objects the walk below iterates, not
    # copies) purely to look the resolved identity back up per placeable; nothing
    # depends on object identity beyond that.
    identities = {}
    disambiguation_input = {}
    for placeable in owned:
        points_here = placeable.findall("productionPoint")
        if points_here or placeable.findall(B9_MOD_ELEMENT):
            entry = list(
                placeable_identity(placeable, farm_id, install_dir, mods_dir))
            identities[id(placeable)] = entry
            # ⛔ F2 (review-d4d5c-opus): a placeable with ONLY a watering
            # block and no <productionPoint> produces no point row at all, so
            # it must not take a D5 numbering slot -- disambiguate_names()
            # only sees placeables that actually own a productionPoint. Left
            # unfiltered, a watering-only twin sharing a name with one real
            # point would number that lone point "X #1" with no "#2" ever
            # emitted, which reads as a missing second building.
            if points_here:
                disambiguation_input[id(placeable)] = entry
    disambiguate_names(disambiguation_input)

    for placeable in owned:
        points = placeable.findall("productionPoint")
        watering_blocks = placeable.findall(B9_MOD_ELEMENT)

        if points or watering_blocks:
            placeable_id, name, name_resolution_source, name_reason = (
                identities[id(placeable)])

        for point in points:
            production_points += 1
            where = f"{name!r} ({placeable_id})"
            owned_points.append({
                "placeable_id": placeable_id,
                "placeable_name": name,
                "name_resolution_source": name_resolution_source,
                "name_unresolved_reason": name_reason,
                # DEC-212: the emitter's fallback for a failed resolution
                # derives a readable label from the FILE name rather than the
                # hex uniqueId -- it needs the filename to do that.
                "filename": placeable.attrib.get("filename", "") or "",
                "absent_attributes": [],
                "defaulted_attributes": [],
            })

            # b3 -- one row per production line.
            for line in point.findall("production"):
                production_id = line.attrib.get("id")
                is_enabled = line.attrib.get("isEnabled")
                if production_id is None or is_enabled is None:
                    missing = "id" if production_id is None else "isEnabled"
                    fail(
                        f"<production> on {where} has no {missing!r} attribute -- "
                        "savegame_placeables.xsd:1234-1240 declares both. Refusing "
                        "to substitute a default for a missing schema attribute.",
                        calibration_needed=True,
                    )
                lines.append({
                    "placeable_id": placeable_id,
                    "placeable_name": name,
                    "production_id": production_id,
                    # RAW, not bool -- g_bool is a restriction of xs:string, and
                    # sec. 6.5's hazard table requires an xs:boolean citation that
                    # does not exist in any of this install's 88 XSDs. See the
                    # module docstring.
                    "is_enabled": is_enabled,
                    "absent_attributes": [],
                    "defaulted_attributes": [],
                })

            # b4 -- absent is NOT zero. The XSD gives this attribute no default
            # while giving storage/@fillLevel one; that contrast is the citation.
            raw_costs = point.attrib.get("productionCostsToClaim")
            if raw_costs is None:
                costs_absent += 1
            else:
                costs.append({
                    "placeable_id": placeable_id,
                    "placeable_name": name,
                    "costs_to_claim": coerce(
                        raw_costs, "float", "productionCostsToClaim", where),
                    "absent_attributes": [],
                    "defaulted_attributes": [],
                })

            # b6 -- same rule, same reason.
            raw_cooldown = point.attrib.get("palletSpawnCooldown")
            if raw_cooldown is None:
                cooldowns_absent += 1
            else:
                cooldowns.append({
                    "placeable_id": placeable_id,
                    "placeable_name": name,
                    "pallet_spawn_cooldown": coerce(
                        raw_cooldown, "int", "palletSpawnCooldown", where),
                    "absent_attributes": [],
                    "defaulted_attributes": [],
                })

            # b5 -- two sibling element kinds, one section. Both are minOccurs=0
            # ELEMENTS whose presence IS the configuration.
            for mode, tag in (("auto_deliver", "autoDeliverFillType"),
                              ("direct_sell", "directSellFillType")):
                for element in point.findall(tag):
                    text = (element.text or "").strip()
                    if not text:
                        fail(
                            f"<{tag}> on {where} is present but empty. The element "
                            "exists to name a fillType; an empty one is a schema "
                            "surprise, and reading it as 'nothing configured' "
                            "would erase a configuration the file is asserting.",
                            calibration_needed=True,
                        )
                    delivery.append({
                        "placeable_id": placeable_id,
                        "placeable_name": name,
                        "mode": mode,
                        "fill_type": text,
                        "absent_attributes": [],
                        "defaulted_attributes": [],
                    })

            # Storage fill LEVELS. The ceiling is NOT here -- see the docstring.
            for store in point.findall("storage"):
                for node in store.findall("node"):
                    fill_type = node.attrib.get("fillType")
                    if fill_type is None:
                        fail(
                            f"<storage><node> on {where} has no fillType attribute "
                            "-- savegame_placeables.xsd:1250-1253 declares it. A "
                            "fill level with no fill type names no commodity.",
                            calibration_needed=True,
                        )
                    # THIS is the one attribute whose absence IS zero, and by
                    # citation: the XSD declares default="0" on it and on no other
                    # attribute this script reads.
                    raw_level = node.attrib.get("fillLevel", "0")
                    # `defaulted_attributes` rather than a per-field
                    # `fill_level_was_defaulted` boolean. A defaulted value and
                    # an observed one are different provenance, and this
                    # codebase recorded that difference three different ways --
                    # a boolean here, NOTHING for read_bales_pallets.py's three
                    # cited defaults, and no case at all in the definitions
                    # reader. A per-field flag is opt-in, which is exactly the
                    # failure `absent_attributes` exists to close.
                    #
                    # This attribute IS a value by citation: the XSD declares
                    # default="0" on it and on no other attribute this script
                    # reads, so the key is present and holds 0.0 -- it is simply
                    # not OBSERVED, and the row says which.
                    storage_levels.append({
                        "placeable_id": placeable_id,
                        "placeable_name": name,
                        "fill_type": fill_type,
                        "fill_level": coerce(raw_level, "float", "fillLevel", where),
                        "absent_attributes": [],
                        "defaulted_attributes": (
                            [] if "fillLevel" in node.attrib else ["fill_level"]),
                    })

        # b9 -- a MOD element, absent from the base schema entirely.
        for block in watering_blocks:
            for spec in block.findall("AutomaticWateringSpecialization"):
                raw_auto = spec.attrib.get("AutoWatering")
                if raw_auto is None:
                    fail(
                        f"<AutomaticWateringSpecialization> on {name!r} "
                        f"({placeable_id}) has no AutoWatering attribute. The "
                        "element exists to carry exactly that state; refusing to "
                        "invent one.",
                        calibration_needed=True,
                    )
                watering.append({
                    "placeable_id": placeable_id,
                    "placeable_name": name,
                    # RAW twice over: g_bool is xs:string, and this element is not
                    # in the base XSD at all so there is nothing to cite.
                    "auto_watering": raw_auto,
                    "absent_attributes": [],
                    "defaulted_attributes": [],
                })

    sections = {}

    # ---- OWNED PRODUCTION POINTS -------------------------------------------
    #
    # ⛔ THE COUNT OF POINTS IS NOT DERIVABLE FROM THE LINE ROWS, and the FARM
    # tab shipped a wrong number for exactly that reason. `production_lines`
    # emits one row per <production> child, so a placeable that owns a
    # <productionPoint> with NO children contributes NOTHING to it -- and a
    # consumer counting distinct placeable_ids over those rows counts only the
    # points that happen to have lines configured. Measured on the owner's
    # savegame1 (2026-09-03): 27 owned placeables carry a <productionPoint>,
    # 23 declare <production> children and 4 do not, so the tab read 23 owned
    # production points against a farm that owns 27.
    #
    # ⚠ NOT A MOD QUIRK. One of the four silent points is a BASE-GAME placeable
    # (data/placeables/mapEU/potatoProcessingPlant/), and the trigger is
    # ordinary play: buy a production building, do not configure a line yet.
    #
    # ⭐ A RECORD_LIST, NOT A BARE SCALAR. The count is `count`, which every
    # other section in this envelope already guarantees equals len(data) -- so
    # the number a consumer reads cannot drift from the rows that justify it.
    # A first draft published a "scalar" shape carrying the integer twice; it
    # broke three of this domain's suite-wide invariants (count == len(data),
    # the per-row provenance lists, and the fixed section set) because those
    # invariants are what make sections comparable. Naming each point also lets
    # a reader see WHICH buildings were being dropped, which is how the defect
    # was diagnosed in the first place.
    #
    # The measurement itself is not new: the walk above already visited every
    # container, and used the total only inside other sections' PROSE.
    if owned_points:
        pp_status, pp_reason = "ok", None
    else:
        pp_status = "unknown_by_design"
        pp_reason = (
            f"farm {farm_id} owns no <productionPoint> placeables. The placeable "
            "set was read in full and none carries a production point, so the "
            "count is a MEASURED ZERO -- an observation about a present file, "
            "not an inference from an absent one. A consumer must render it as "
            "0, never as `unknown`."
        )
    sections["production_points"] = {
        "status": pp_status,
        "reason": pp_reason,
        "shape": "record_list",
        # The b3 CONTAINERS. No new capability is claimed -- the module's
        # CAPABILITY_IDS is unchanged -- because this publishes containers the
        # b3 walk already visited.
        "capability_ids": ["b3"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            # D4/D5: which hop actually produced placeable_name ("literal",
            # "l10n_inline", "l10n_external", "no_filename", "unresolved") and,
            # only when it is "<unnamed>" because resolution failed, WHY --
            # never null (sec. 6.2 one level in: a row never carries a null),
            # so this is a list, empty when resolution was not needed.
            # ⚠ NAMED name_resolution_source, NOT name_source -- fix round 2
            # (F4): emit_productions_xml.py already owns a differently-valued
            # name_source/nameSource vocabulary the Lua GUI reads. See
            # placeable_identity()'s docstring.
            "name_resolution_source": "raw",
            "name_unresolved_reason": "raw",
            # DEC-212: the placeable's own filename, so a failed resolution
            # can be labelled from the file name instead of the hex uniqueId.
            # "" for preplaced points, which carry no filename at all.
            "filename": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        # Nothing here is coerced: these are the identities of containers that
        # were read, not values lifted out of attributes.
        "typing_guarantee": {},
        "identity_fields": ["placeable_id"],
        "empty_means": "farm_has_none",
        # The containers were READ, not assumed absent -- sec. 6.3.1 rule 4,
        # the same licence production_lines relies on.
        "absence_guarantee": None,
        "source_elements": ["placeables.xml:placeable/productionPoint"],
        "blocked_by": None,
        "count": len(owned_points),
        "data": owned_points,
    }

    # ---- b3 -----------------------------------------------------------------
    if lines:
        b3_status, b3_reason = "ok", None
    elif production_points:
        b3_status = "unknown_by_design"
        b3_reason = (
            f"farm {farm_id}'s {production_points} production point(s) are present "
            "and declare no <production> lines at all -- this farm runs no "
            "production lines. The containers were read directly, so this is an "
            "observation, not an inference."
        )
    else:
        b3_status = "unknown_by_design"
        b3_reason = (
            f"farm {farm_id} owns no <productionPoint> placeables -- it runs no "
            "productions. The placeable set was read in full and none carries a "
            "production point, so this is an observation about a present file, "
            "not an inference from an absent one."
        )
    sections["production_lines"] = {
        "status": b3_status,
        "reason": b3_reason,
        "shape": "record_list",
        "capability_ids": ["b3"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            "production_id": "raw",
            "is_enabled": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        # No coerced field, so no citation is owed. An empty map is the honest
        # value here, not a missing key -- the key itself is REQUIRED (sec. 6.2).
        "typing_guarantee": {},
        "identity_fields": ["placeable_id", "production_id"],
        "empty_means": "farm_has_none",
        # The container -- <productionPoint> -- is PRESENT and was read. Nothing
        # is being inferred from an absent container, so sec. 6.3.1 rule 4 applies
        # and no licence is owed.
        "absence_guarantee": None,
        "source_elements": ["placeables.xml:placeable/productionPoint/production"],
        "blocked_by": None,
        "count": len(lines),
        "data": lines,
    }

    # ---- b4 -----------------------------------------------------------------
    if costs:
        b4_status = "ok"
        b4_reason = (
            f"{len(costs)} of farm {farm_id}'s {production_points} production "
            f"point(s) carry a productionCostsToClaim attribute; {costs_absent} do "
            "not. The absent ones are NOT reported as zero: the XSD gives this "
            "attribute no default while giving storage/@fillLevel default=\"0\", so "
            "absence here is unlicensed and 'nothing to claim' is not the same "
            "fact as 'the file does not say'."
        ) if costs_absent else None
    elif production_points:
        # Nothing to license the reading "this farm owes nothing", so the
        # conservative default stands (sec. 6.3.1 rule 1).
        b4_status = "unavailable"
        b4_reason = (
            f"none of farm {farm_id}'s {production_points} production point(s) "
            "carries a productionCostsToClaim attribute. The XSD declares it "
            "g_float with NO default, so an absent attribute is not licensed to "
            "read as 0.0 -- whether this farm owes unclaimed production costs "
            "cannot be determined from this file."
        )
    else:
        b4_status = "unknown_by_design"
        b4_reason = (
            f"farm {farm_id} owns no <productionPoint> placeables, so there is no "
            "production for costs to accrue against."
        )
    sections["production_costs_to_claim"] = {
        "status": b4_status,
        "reason": b4_reason,
        "shape": "record_list",
        "capability_ids": ["b4"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            "costs_to_claim": "float",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        "typing_guarantee": {
            "costs_to_claim":
                "savegame_placeables.xsd:1265 declares @productionCostsToClaim as "
                + _G_FLOAT,
        },
        "identity_fields": ["placeable_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "placeables.xml:placeable/productionPoint@productionCostsToClaim"],
        "blocked_by": None,
        "count": len(costs),
        "data": costs,
    }

    # ---- b5 -----------------------------------------------------------------
    if delivery:
        b5_status, b5_reason = "ok", None
    elif production_points:
        # The CONTAINER is present and holds no delivery elements. That is
        # sec. 6.3.1 rule 4 -- present-but-empty -- and it needs no licence,
        # unlike b10's absent container. The distinction is the whole point of
        # the rule: we read a container that is right there.
        b5_status = "unknown_by_design"
        b5_reason = (
            f"farm {farm_id}'s {production_points} production point(s) are present "
            "and hold no <autoDeliverFillType> or <directSellFillType> element -- "
            "no output is configured for auto-delivery or direct sale. The "
            "elements' PRESENCE is the configuration, and the containers holding "
            "them were read directly, so this is an observation, not an inference."
        )
    else:
        b5_status = "unknown_by_design"
        b5_reason = (
            f"farm {farm_id} owns no <productionPoint> placeables, so there is no "
            "output to configure for delivery or direct sale."
        )
    sections["delivery_modes"] = {
        "status": b5_status,
        "reason": b5_reason,
        "shape": "record_list",
        "capability_ids": ["b5"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            "mode": "raw",
            "fill_type": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        "typing_guarantee": {},
        "identity_fields": ["placeable_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "placeables.xml:placeable/productionPoint/autoDeliverFillType",
            "placeables.xml:placeable/productionPoint/directSellFillType",
        ],
        "blocked_by": None,
        "count": len(delivery),
        "data": delivery,
    }

    # ---- b6 -----------------------------------------------------------------
    if cooldowns:
        b6_status = "ok"
        b6_reason = (
            f"{len(cooldowns)} of farm {farm_id}'s {production_points} production "
            f"point(s) carry a palletSpawnCooldown attribute; {cooldowns_absent} do "
            "not, and those are not reported as zero for the same reason b4's are "
            "not -- the XSD declares no default."
        ) if cooldowns_absent else None
    elif production_points:
        b6_status = "unavailable"
        b6_reason = (
            f"none of farm {farm_id}'s {production_points} production point(s) "
            "carries a palletSpawnCooldown attribute. The XSD declares it g_int "
            "with NO default, so an absent attribute is not licensed to read as 0 "
            "-- whether any pallet spawner is on cooldown cannot be determined "
            "from this file. Reporting 'no spawner is on cooldown' would be a "
            "positive claim about the farm that nothing here supports."
        )
    else:
        b6_status = "unknown_by_design"
        b6_reason = (
            f"farm {farm_id} owns no <productionPoint> placeables, so there is no "
            "pallet spawner to be on cooldown."
        )
    sections["pallet_spawn_cooldown"] = {
        "status": b6_status,
        "reason": b6_reason,
        "shape": "record_list",
        "capability_ids": ["b6"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            "pallet_spawn_cooldown": "int",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        "typing_guarantee": {
            "pallet_spawn_cooldown":
                "savegame_placeables.xsd:1262 declares @palletSpawnCooldown as "
                + _G_INT,
        },
        "identity_fields": ["placeable_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "placeables.xml:placeable/productionPoint@palletSpawnCooldown"],
        "blocked_by": None,
        "count": len(cooldowns),
        "data": cooldowns,
    }

    # ---- storage fill levels (b7's savegame half) ---------------------------
    if storage_levels:
        s_status = "ok"
        s_reason = (
            "fill LEVELS only. The savegame records what a production storage "
            "HOLDS; it does not record what it can hold. The capacity ceiling "
            "lives in the placeable's definition file in the game install or map "
            "mod (b7), which this savegame-only reader does not open -- so no "
            "percentage-full, and no 'silo full' verdict, can be derived from "
            "this section alone."
        )
    elif production_points:
        s_status = "unknown_by_design"
        s_reason = (
            f"farm {farm_id}'s {production_points} production point(s) are present "
            "and declare no <storage><node> -- these production points hold "
            "nothing. The containers were read directly, so this is an "
            "observation, not an inference."
        )
    else:
        s_status = "unknown_by_design"
        s_reason = (
            f"farm {farm_id} owns no <productionPoint> placeables, so it has no "
            "production storage."
        )
    sections["storage_fill_levels"] = {
        "status": s_status,
        "reason": s_reason,
        "shape": "record_list",
        "capability_ids": ["b7"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            "fill_type": "raw",
            "fill_level": "float",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        "typing_guarantee": {
            "fill_level":
                "savegame_placeables.xsd:1247 declares @fillLevel as " + _G_FLOAT
                + ' with default="0", so an absent attribute IS zero by citation '
                  "-- the one attribute in this domain for which that is true",
        },
        "identity_fields": ["placeable_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "placeables.xml:placeable/productionPoint/storage/node"],
        "blocked_by": None,
        "count": len(storage_levels),
        "data": storage_levels,
    }

    # ---- b9 -----------------------------------------------------------------
    if watering:
        w_status, w_reason = "ok", None
    else:
        # The mod element is absent. Unlike the base-schema sections above there
        # is no schema here AT ALL, so there is nothing that could license
        # reading absence as "the mod is installed and everything is off". The
        # honest reading is that we cannot tell an uninstalled mod from an
        # installed one that wrote nothing.
        w_status = "unavailable"
        w_reason = (
            f"no <{B9_MOD_ELEMENT}> element on any of farm {farm_id}'s "
            "placeables. This is a MOD element with no entry in the base schema, "
            "so nothing licenses reading its absence as a state: a farm whose "
            "greenhouse-watering mod is not installed and a farm whose mod is "
            "installed but wrote nothing are indistinguishable from this file."
        )
    sections["greenhouse_auto_watering"] = {
        "status": w_status,
        "reason": w_reason,
        "shape": "record_list",
        "capability_ids": ["b9"],
        "typing": {
            "placeable_id": "raw",
            "placeable_name": "raw",
            "auto_watering": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
        },
        # Deliberately empty and it is NOT an oversight: the base XSD does not
        # declare this mod element (grep -c -> 0), so no citation exists to make.
        # sec. 6.5 rule 1's default stands.
        "typing_guarantee": {},
        "identity_fields": ["placeable_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "placeables.xml:placeable/" + B9_MOD_ELEMENT
            + "/AutomaticWateringSpecialization"],
        "blocked_by": None,
        "count": len(watering),
        "data": watering,
    }

    top_status, top_reason = roll_up(sections)

    emit({
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN,
        "set": SET,
        "farm_id": farm_id,
        "capability_ids": list(CAPABILITY_IDS),
        "provenance": provenance,
        "status": top_status,
        "reason": top_reason,
        "sections": sections,
    })


if __name__ == "__main__":
    main()
