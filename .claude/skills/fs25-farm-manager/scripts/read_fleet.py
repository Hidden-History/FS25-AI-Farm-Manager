"""
DOMAIN SCRIPT (fleet set) -- vehicle detail, emitted in the sec. 6.2 envelope.

Usage: python3 read_fleet.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

Built against architecture-farm-manager-cached-state.md rev 4. Follows
read_livestock.py, which is the ratified template: the sec. 6.2 envelope with
sec. 6.3.1's absence rule, sec. 6.3.3's roll-up and sec. 6.5's typing rule.

Capabilities, from the capability inventory's bucket (b):

    b41  vehicle configuration detail  -- vehicles.xml (SAVE), inventory sec. 2.7
    b18  livestock-trailer occupants   -- savegame_vehicles.xsd (XSD), inventory sec. 2.3

Reads ONE file, read-only: vehicles.xml. Nothing here writes to the savegame,
ever. The only writes this process performs are to stdout.

OWNERSHIP FILTERING IS NOT OPTIONAL
-----------------------------------
Measured on the live save: vehicles.xml holds 141 <vehicle> elements, of which
114 are farmId=1 and 27 are farmId=0 -- the map's own train rolling stock, not
the player's fleet. A reader that skips the farmId filter describes the MAP, not
the FARM, and the first rows it meets (the BNSF locomotive and its hoppers) are
exactly the ones that will mislead it. Every vehicle considered here is filtered
on the <vehicle> element's own farmId attribute. This is the same trap
read_livestock.py documents for placeables, where 22 of 25 husbandries are map
furniture.

TYPING (sec. 6.5) -- AND ONE SUBTLETY THAT WILL BITE EVERY FUTURE BUILDER
-------------------------------------------------------------------------
Unlike the weather domain -- where NO savegame schema exists at all, so
everything ships raw -- vehicles.xml HAS one: savegame_vehicles.xsd. So rule 5
is live here: where a guarantee exists the coercion is MANDATORY, not merely
permitted, and every coerced field carries its own citation (rule 2).

⚠ `isActive` IS DECLARED g_bool AND STILL SHIPS RAW. This looks like a rule-5
violation and is not. Measured at savegame_vehicles.xsd:60-63:

    <xs:simpleType name="g_bool">
        <xs:restriction base="xs:string">
            <xs:pattern value="true|false"/>

g_bool restricts **xs:string**, not xs:boolean. sec. 6.5's hazard table is
explicit about exactly this case -- "Boolean-as-string: `bool` ONLY with an XSD
`xs:boolean` citation; else `raw`" -- and it is the row that DEFINES what counts
as a bool guarantee. No xs:boolean citation exists, so no guarantee exists, so
rule 5 never fires and rule 1's default stands. There is no conflict between the
two rules; the hazard table is what tells you the guarantee is not there.

This matters far beyond this script: EVERY g_bool in every FS25 savegame schema
behaves this way, so every future domain reading a boolean-looking attribute
inherits this answer. Recorded here rather than re-derived 39 times.

`id` is declared g_string ("Save id") despite holding "1", "2", "3". It is raw
twice over: the schema types it as a string, and it is declared in
identity_fields, whose rule-5 exception keeps identifiers uncoerced however
well-typed they are. An identifier that happens to look numeric is not a
quantity -- the same reason b10's subType stays raw.

b18 IS `unavailable`, AND THAT IS THE ABSENCE RULE WORKING
----------------------------------------------------------
This save carries ZERO <livestockTrailer> elements -- 0 across all 141 vehicles,
not 0 across the 114 owned ones. The element IS schema-declared
(savegame_vehicles.xsd:1506, minOccurs="0", with animal children carrying
age/health/numAnimals/reproduction/subType -- the same shape as b10).

It would be easy, and wrong, to report `unknown_by_design / farm_has_none` here
by analogy with b10. sec. 6.3.1 rule 1 forbids it: absence is not evidence until
something licenses it, and NOTHING licenses this one.

  - minOccurs="0" is NOT a licence. sec. 6.3.2 says so in its own words: the
    XSD's minOccurs="0" "says it MAY be absent, which is permission, not
    behaviour." It establishes absence is legal, never that the engine omits
    the element when a trailer is empty.
  - ARCH-R3-01 is NOT a licence here. That ruling is scoped to
    husbandryAnimals/clusters. Stretching a ruling to a second element by
    analogy is precisely the laundering the `kind` field exists to prevent, and
    inventing an ARCH-R3-02 is not a domain script's call to make.

So b18 reports `unavailable` with the measurement attached, and the fleet domain
rolls up to `partial` (sec. 6.3.3 rule 1). That is the honest answer: we cannot
tell "this farm owns no livestock trailer" from "it owns one that the engine
wrote no element for". What would settle it is one save containing a livestock
trailer with zero animals aboard -- an owner live test, exactly as ARCH-R3-01's
was.

Output contract:
    - Could-not-run -- bad args, unreadable vehicles.xml, unknown farm_id --
      emits a top-level {"error": ...} and exits 1 (sec. 6.3, DEC-001). Never [],
      never {}, never None, never a coerced guess.
    - The script ran -- the envelope is emitted with both sections always
      present. A section is never suppressed, on any farm, ever.
"""
import hashlib
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

SCHEMA_VERSION = 1
GENERATOR = "read_fleet.py"
GENERATOR_VERSION = "1.0.0"
USAGE = "read_fleet.py <savegame_dir> [--farm-id N]"

DOMAIN = "fleet"
SET = "fleet"
CAPABILITY_IDS = ["b18", "b41"]

# savegame_vehicles.xsd:1242-1259 declares five attributes on <configuration>.
# The first three are REQUIRED here because they were measured present on
# 1199/1199 elements: a missing one is a schema surprise, not a default.
CONFIG_REQUIRED = ("name", "id", "isActive")

# The other two are genuinely optional and were measured absent on 1199/1199 on
# this save. They are emitted ONLY when present -- never as null, and never as
# the XSD's declared default. `color` declares default="1 1 1", and writing that
# default into the output would be inventing a colour the save never recorded,
# which is substituting a default for absence (sec. 6.5 rule 3's sibling).
CONFIG_OPTIONAL = ("color", "materialTemplateName")

# sec. 6.5 rules 1-2 and 5. Everything here is raw, and every entry has a
# measured reason -- see the module docstring on g_bool. There is no
# typing_guarantee map for b41 because NOTHING is coerced: rule 2 requires a
# citation for a coercion, and a citation for a non-coercion would be a claim
# about a guarantee that is not being used.
CONFIG_TYPING = {
    "vehicle_unique_id": "raw",
    "name": "raw",
    "id": "raw",
    "isActive": "raw",
    "color": "raw",
    "materialTemplateName": "raw",
}

CONFIG_TYPING_GUARANTEE = {
    "*": (
        "NOTHING IS COERCED, and each for a cited reason. name/id/"
        "materialTemplateName are g_string -> xs:string "
        "(savegame_vehicles.xsd:7-9); color is g_vector_3, a pattern-restricted "
        "string (:85-88). isActive is g_bool, which restricts **xs:string** "
        "with pattern true|false (:60-63) and is NOT xs:boolean -- sec. 6.5's "
        "hazard table requires an xs:boolean citation for a bool coercion and "
        "there is none, so rule 1's default stands. `id` is additionally an "
        "identity field, which rule 5's exception keeps raw regardless."
    )
}

# sec. 7.3's promoted general rule: a record_list drawn from a per-vehicle
# container MUST carry the owning vehicle's identity, or two configurations on
# different machines are indistinguishable. uniqueId is measured present on
# 141/141 vehicles with zero duplicates.
CONFIG_IDENTITY = ["vehicle_unique_id", "id"]

# savegame_vehicles.xsd:1511-1519. Same five attributes as b10's <animal>, and
# the same typing answer: four g_int -> int (MANDATORY under rule 5), subType
# g_string -> raw.
TRAILER_ANIMAL_ATTRS = ("age", "health", "numAnimals", "reproduction", "subType")

_G_INT = "g_int -> xs:restriction base=xs:integer (savegame_vehicles.xsd:50-53)"

TRAILER_TYPING = {
    "vehicle_unique_id": "raw",
    "animalType": "raw",
    "age": "int",
    "health": "int",
    "numAnimals": "int",
    "reproduction": "int",
    "subType": "raw",
}

TRAILER_TYPING_GUARANTEE = {
    "age": "savegame_vehicles.xsd:1511 declares @age as " + _G_INT,
    "health": "savegame_vehicles.xsd:1513 declares @health as " + _G_INT,
    "numAnimals": "savegame_vehicles.xsd:1515 declares @numAnimals as " + _G_INT,
    "reproduction": "savegame_vehicles.xsd:1517 declares @reproduction as " + _G_INT,
}

TRAILER_IDENTITY = ["vehicle_unique_id"]

# Element-level, never file-level (sec. 6.2). vehicles.xml feeds both sections
# and a file-level locator could not tell them apart -- the same distinction
# that keeps b40 out of BUG-014's net.
SRC_CONFIG = ["vehicles.xml:vehicle/configuration"]
SRC_TRAILER = ["vehicles.xml:vehicle/livestockTrailer/animal"]


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


def parse_farm_id_arg(argv):
    """Pull --farm-id N (or --farm-id=N) out of argv; default 1.

    Returns (farm_id, error_or_None).

    BOTH SPELLINGS, AND NOTHING SWALLOWED. read_livestock.py's parser used to
    understand only the space-separated form and to drop every argument it did
    not recognise, so `--farm-id=15` selected farm 1 and exited 0 -- a
    confidently reported WRONG FARM. The same trap is live here: 27 of this
    save's 141 vehicles belong to farmId=0, so a silently defaulted farm id
    reports the map's train as the player's fleet.
    """
    farm_id = 1
    args = argv[2:]  # argv[0] = script, argv[1] = savegame_dir (already consumed)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--farm-id":
            if i + 1 >= len(args):
                return None, f"usage: {USAGE} -- --farm-id given with no value"
            raw = args[i + 1]
            i += 2
        elif arg.startswith("--farm-id="):
            raw = arg.split("=", 1)[1]
            i += 1
        else:
            return None, (
                f"unrecognised argument {arg!r} -- refusing to ignore it and "
                f"report the default farm. usage: {USAGE}")
        try:
            farm_id = int(raw)
        except ValueError:
            return None, f"--farm-id must be an integer, got {raw!r}"
    return farm_id, None


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


def section(status, reason, shape, cap_ids, typing, guarantee, identity,
            empty_means, absence_guarantee, source_elements, count, data):
    """One sec. 6.2 section, with every declared key present.

    ALL THE KEYS, ALWAYS. sec. 6.2: a MISSING key is a build failure, not a
    default, because defaulting is how a guard gets silently skipped. Routing
    every section through one constructor is what makes that structural rather
    than something each call site must remember.

    `blocked_by` is None for every section in this domain and is NOT a parameter
    -- vehicles.xml carries no element on BUG-014's block list, whose only entry
    is farms.xml:farm/finances/stats/fieldPurchase. (Re-keyed from BUG-012 and
    narrowed from two entries by DEC-057 ⑥/⑧, which dropped
    infoLayer_farmlands.grle:*. Neither change reaches this domain -- it read
    none of them.) Making it a parameter would invite a caller to pass one.
    """
    return {
        "status": status,
        "reason": reason,
        "shape": shape,
        "capability_ids": list(cap_ids),
        "typing": dict(typing),
        "typing_guarantee": dict(guarantee),
        "identity_fields": list(identity),
        "empty_means": empty_means,
        "absence_guarantee": absence_guarantee,
        "source_elements": list(source_elements),
        "blocked_by": None,
        "count": count,
        "data": data,
    }


def read_vehicle_configurations(owned, farm_id):
    """b41 -- every <configuration>, carrying its owning vehicle's identity.

    Returns (section, error_or_None).

    1,199 configuration elements exist across the 141 vehicles on this save and
    1,049 of them sit on the 114 farm-1 machines. read_vehicles.py emits
    per-vehicle price/age/damage/fuel/fill units and never touches these, so
    nothing here restates a claim another script already owns (DEC-048 (1)).
    """
    rows = []
    for vehicle in owned:
        unique_id = vehicle.attrib.get("uniqueId")
        if unique_id is None:
            return None, (
                "a <vehicle> on farm %s carries <configuration> elements but no "
                "uniqueId attribute -- savegame_vehicles.xsd declares it, and it "
                "is the only vehicle identity the schema defines. Refusing to "
                "emit configuration rows that cannot be attributed to a specific "
                "machine (sec. 7.3)." % farm_id)
        for cfg in vehicle.findall("configuration"):
            row = {"vehicle_unique_id": unique_id}
            for attr in CONFIG_REQUIRED:
                raw = cfg.attrib.get(attr)
                if raw is None:
                    return None, (
                        "<configuration> on vehicle %r has no %r attribute -- "
                        "savegame_vehicles.xsd:1242-1259 declares it and it was "
                        "measured present on 1199/1199 elements. Refusing to "
                        "substitute a default for a missing schema attribute."
                        % (unique_id, attr))
                row[attr] = raw
            # Optional attributes appear ONLY when the save actually carries
            # them. Never null, never the XSD's declared default -- see
            # CONFIG_OPTIONAL. An absent key here means an absent attribute, and
            # the three required ones above fail loud, so it is unambiguous.
            for attr in CONFIG_OPTIONAL:
                if attr in cfg.attrib:
                    row[attr] = cfg.attrib[attr]
            rows.append(row)

    if not rows:
        # Every owned vehicle was inspected and none carried a <configuration>.
        # The vehicles ARE there and were read, so nothing is being inferred:
        # sec. 6.3.1 rule 4, no licence owed.
        return section(
            "unknown_by_design",
            "farm %s owns %d vehicle(s) and not one carries a <configuration> "
            "element. Every owned vehicle was inspected, so this is an "
            "observation, not an inference." % (farm_id, len(owned)),
            "record_list", ["b41"], CONFIG_TYPING, CONFIG_TYPING_GUARANTEE,
            CONFIG_IDENTITY, "farm_has_none", None, SRC_CONFIG, 0, []), None

    return section(
        "ok", None, "record_list", ["b41"], CONFIG_TYPING,
        CONFIG_TYPING_GUARANTEE, CONFIG_IDENTITY, "farm_has_none", None,
        SRC_CONFIG, len(rows), rows), None


def read_livestock_trailer_occupants(all_vehicles, owned, farm_id):
    """b18 -- animals aboard livestock trailers. Returns (section, error_or_None).

    When the element is present this reads exactly like b10 and types identically
    (four g_int -> int, subType raw). When it is ABSENT everywhere -- which is
    this save -- the answer is `unavailable`, NOT farm_has_none. The module
    docstring carries the full argument; the short version is that minOccurs="0"
    is permission, not behaviour, and ARCH-R3-01 does not reach this element.

    The measurement is carried in the reason rather than left to a reader to
    reproduce, because "not available" without the measurement that proves it is
    the absence-as-data defect this project keeps paying for.
    """
    containers = [(v, t) for v in owned for t in v.findall("livestockTrailer")]
    map_wide = sum(len(v.findall("livestockTrailer")) for v in all_vehicles)

    if not containers:
        return section(
            "unavailable",
            "no <livestockTrailer> element on any of farm %s's %d owned "
            "vehicle(s); %d across all %d vehicles map-wide. The element is "
            "schema-declared (savegame_vehicles.xsd:1506, minOccurs=\"0\") but "
            "ABSENT, and nothing licenses reading that absence as data: "
            "minOccurs=\"0\" establishes absence is LEGAL, never that the engine "
            "omits the element when a trailer carries no animals (sec. 6.3.2 -- "
            "permission, not behaviour), and ruling ARCH-R3-01 is scoped to "
            "husbandryAnimals/clusters and does not reach here. So this is "
            "unavailable by sec. 6.3.1 rule 1, not farm_has_none: we cannot tell "
            "'this farm owns no livestock trailer' from 'it owns one the engine "
            "wrote no element for'. Corroborating but NOT licensing: 0 of %d "
            "vehicle filenames match livestock/animal/cattle/transport. What "
            "would settle it is one save holding a livestock trailer with zero "
            "animals aboard."
            % (farm_id, len(owned), map_wide, len(all_vehicles), len(all_vehicles)),
            "record_list", ["b18"], TRAILER_TYPING, TRAILER_TYPING_GUARANTEE,
            TRAILER_IDENTITY, None, None, SRC_TRAILER, 0, None), None

    rows = []
    for vehicle, trailer in containers:
        unique_id = vehicle.attrib.get("uniqueId")
        if unique_id is None:
            return None, (
                "a <vehicle> on farm %s holds a <livestockTrailer> but has no "
                "uniqueId attribute. Refusing to emit animal rows that cannot be "
                "attributed to a specific trailer (sec. 7.3)." % farm_id)
        for animal in trailer.findall("animal"):
            # animalType is OMITTED when the trailer does not carry it, never
            # emitted as null -- a null here would read as "this trailer has no
            # animal type" where the truth is "the attribute was not there". Same
            # rule as CONFIG_OPTIONAL above.
            row = {"vehicle_unique_id": unique_id}
            if "animalType" in trailer.attrib:
                row["animalType"] = trailer.attrib["animalType"]
            for attr in TRAILER_ANIMAL_ATTRS:
                raw = animal.attrib.get(attr)
                if raw is None:
                    return None, (
                        "<animal> aboard trailer %r has no %r attribute -- "
                        "savegame_vehicles.xsd:1511-1519 declares it. Refusing to "
                        "substitute a default for a missing schema attribute."
                        % (unique_id, attr))
                if TRAILER_TYPING[attr] == "int":
                    try:
                        row[attr] = int(raw)
                    except ValueError:
                        # sec. 6.5 rule 3: a value that fails its declared
                        # coercion is an error, never a fallback.
                        return None, (
                            "<animal %s=%r> aboard trailer %r is not an integer, "
                            "but the XSD declares it g_int. Refusing to coerce or "
                            "drop it." % (attr, raw, unique_id))
                else:
                    row[attr] = raw
            rows.append(row)

    if not rows:
        # The container is RIGHT THERE and holds no animals. sec. 6.3.1 rule 4 --
        # nothing inferred, so absence_guarantee stays null. This is the branch
        # that would retire the `unavailable` above on a save that has one.
        return section(
            "unknown_by_design",
            "%d <livestockTrailer> container(s) on farm %s are present and hold "
            "no <animal> rows -- these trailers are empty. The container was "
            "found, so this is an observation, not an inference."
            % (len(containers), farm_id),
            "record_list", ["b18"], TRAILER_TYPING, TRAILER_TYPING_GUARANTEE,
            TRAILER_IDENTITY, "farm_has_none", None, SRC_TRAILER, 0, []), None

    return section(
        "ok", None, "record_list", ["b18"], TRAILER_TYPING,
        TRAILER_TYPING_GUARANTEE, TRAILER_IDENTITY, "farm_has_none", None,
        SRC_TRAILER, len(rows), rows), None


def roll_up(sections):
    """Top-level status/reason -- sec. 6.3.3, rev 4. TOTAL, ORDERED, FIRST MATCH WINS.

        1. ANY section unavailable or partial -> "partial"
        2. EVERY section unknown_by_design    -> "unknown_by_design"
        3. otherwise (>=1 ok, none failed)    -> "ok"

    (Rule 0 -- the script could not run at all -> {"error": ...} + exit 1 -- is
    handled by fail() before any section is built, so it cannot reach here.)

    COPIED FROM read_livestock.py DELIBERATELY, NOT EXTRACTED. Hoisting this
    into xml_utils.py would breach TECH-DEBT-023; the duplication here is by
    design and is the ratified call, so a future reader tempted to "clean it up"
    should read that ticket first.

    RULE 1 OUTRANKS RULE 2 DELIBERATELY. A domain that is PARTLY unreadable must
    never report the confident unknown_by_design: that status is a positive
    claim about the farm, and a failed section means we do not know. sec. 6.3.3
    -- the status that claims more never wins a tie. On this save that is not
    academic: b18 is unavailable, so this domain reports `partial` even though
    b41 read 1,049 rows cleanly, and that is the correct answer.

    ⚠ THE ORDER IS UNOBSERVABLE, and read_livestock.py's docstring records why:
    the two conditions are DISJOINT, so swapping the branches is a semantic
    no-op and no test can catch it. That finding (M9) is inherited here rather
    than re-learned. The honest guard is the exhaustive truth table in the
    suite, whose teeth ARE measured.
    """
    degraded = sorted(name for name, s in sections.items()
                      if s["status"] in ("unavailable", "partial"))
    if degraded:
        return "partial", "section(s) not fully read: " + "; ".join(
            "%s (%s): %s" % (n, sections[n]["status"], sections[n]["reason"])
            for n in degraded)

    # `sections and` guards the vacuous case: all() over an empty dict is True,
    # which would turn a domain that emitted NO sections into the confident
    # claim "this farm has none". A domain with no sections is a bug (sec. 6.4),
    # never a positive fact.
    if sections and all(s["status"] == "unknown_by_design" for s in sections.values()):
        return ("unknown_by_design",
                "no data of any kind on this farm for this domain")

    return "ok", None


def main():
    # TECH-DEBT-021 item 3: ~15 parsers in this skill consume --help as the
    # savegame path and answer with a file-not-found error. Not repeated here.
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        emit({"usage": USAGE, "domain": DOMAIN, "capability_ids": CAPABILITY_IDS})
        return

    savegame_dir = arg_or_exit(USAGE)
    farm_id, arg_err = parse_farm_id_arg(sys.argv)
    if arg_err:
        fail(arg_err, calibration_needed=False)

    vehicles_path = os.path.join(savegame_dir, "vehicles.xml")
    root, generic = load_xml(vehicles_path)
    if root is None:
        fail(
            f"could not read vehicles.xml: {generic.get('error')}",
            calibration_needed=True,
        )

    provenance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "sources": [file_provenance(vehicles_path)],
    }
    provenance["source_set_hash"] = source_set_hash(provenance["sources"])

    # --- Select by farmId, never by document order --------------------------
    vehicles = list(root.iter("vehicle"))
    if not vehicles:
        fail(
            "vehicles.xml parsed but contained no <vehicle> elements -- "
            "schema may have changed.",
            calibration_needed=True,
            generic_dump=generic,
        )

    farms_seen = set()
    malformed_farm_ids = []
    owned = []
    for vehicle in vehicles:
        raw_id = vehicle.attrib.get("farmId")
        if raw_id is None:
            continue
        try:
            fid = int(raw_id)
        except ValueError:
            malformed_farm_ids.append(raw_id)
            continue
        farms_seen.add(fid)
        if fid == farm_id:
            owned.append(vehicle)

    # A farmId that will not parse is a SCHEMA SURPRISE, and every other schema
    # surprise in this file fails loud. read_livestock.py used to `continue`
    # here -- no counter, no partial, no reason -- so farmId="1.0" made a
    # populated barn vanish and the section reported farm_has_none while citing
    # a ruling to license it. Dropped is not absent, and presenting one as the
    # other is the DEC-001 defect this whole layer exists to prevent.
    if malformed_farm_ids:
        shown = ", ".join(repr(m) for m in sorted(set(malformed_farm_ids))[:5])
        fail(
            f"{len(malformed_farm_ids)} <vehicle> element(s) carry a farmId that "
            f"is not an integer ({shown}). Ownership cannot be established for "
            "them, and skipping them in silence would let a machine disappear "
            "out of the fleet count. Refusing to drop them.",
            calibration_needed=True,
        )

    if not farms_seen:
        fail(
            "vehicles.xml holds <vehicle> elements but not one carries a farmId "
            "attribute -- ownership cannot be established, and reporting an "
            "unowned map's rolling stock as this farm's fleet would be worse "
            "than failing.",
            calibration_needed=True,
        )

    if farm_id not in farms_seen:
        # Not a farm with no vehicles -- a farm that is not in this file at all.
        # Reporting farm_has_none here would convert a lookup miss into a claim
        # about a farm we never found.
        fail(
            f"farm_id {farm_id} owns no vehicles in vehicles.xml. "
            f"Available farm_ids: {sorted(farms_seen)}",
            calibration_needed=False,
        )

    config_section, config_err = read_vehicle_configurations(owned, farm_id)
    if config_err:
        fail(config_err, calibration_needed=True)

    trailer_section, trailer_err = read_livestock_trailer_occupants(
        vehicles, owned, farm_id)
    if trailer_err:
        fail(trailer_err, calibration_needed=True)

    sections = {
        "vehicle_configurations": config_section,
        "livestock_trailer_occupants": trailer_section,
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
