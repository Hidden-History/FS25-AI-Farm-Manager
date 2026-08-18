"""
DOMAIN SCRIPT (b10) -- animal clusters, emitted in the sec. 6.2 domain envelope.

Usage: python3 read_livestock.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

Built against architecture-farm-manager-cached-state.md rev 3. Unlike
read_farm_ledger.py -- which is an explicitly PROVISIONAL shape probe predating
the ruling -- this script emits the ratified reusable template: the sec. 6.2
envelope, with sec. 6.3.1's absence rule and sec. 6.5's typing rule applied.

Reads ONE file, read-only: placeables.xml. Nothing here writes to the savegame,
ever. The only writes this process performs are to stdout.

    b10  <placeable><husbandryAnimals><clusters><animal age= health=
         numAnimals= reproduction= subType=>

THE FILE NAME, AND A CORRECTION TO THE SPEC
-------------------------------------------
sec. 7.3 cites `savegame_placeables.xml` as the source. THAT FILE DOES NOT EXIST.
Measured on this machine: the savegame's data file is `placeables.xml`;
`savegame_placeables.xsd` is the SCHEMA and lives outside the savegame, under
the game install at shared/xml/schema/. `source_elements` below therefore names
`placeables.xml`. The XSD citations are unchanged -- those were always correct,
because they point at the schema, which does exist.

OWNERSHIP FILTERING IS NOT OPTIONAL
-----------------------------------
Measured on the live save: placeables.xml holds 216 placeables, 25 of which are
animal-capable husbandries. TWENTY-TWO of those 25 are farmId=15 -- map
furniture, the map's own decorative barns -- and only THREE belong to the player
(farmId=1). A reader that skips the farmId filter describes the MAP, not the
FARM, and the first rows it meets are the ones that will mislead it. Every
placeable considered here is filtered on the <placeable> element's own farmId
attribute.

ZERO ROWS IS AN ANSWER, NOT A DEFECT
------------------------------------
On this save the correct output is zero animals: all three player husbandries
are empty. Under sec. 6.4 that is a POPULATED section reading
`unknown_by_design` / `empty_means: farm_has_none` / `count: 0` / `data: []`,
not a silent gap and not a reason to delete this script. The plan's own warning
is that treating it as dead code "would be the absence-as-data error one level
up".

WHY AN ABSENT CONTAINER IS READ AS "THE FARM HAS NONE" -- BY RULING
-------------------------------------------------------------------
sec. 6.3.1: absence is not evidence until something licenses it, and the default
for an absent container is `unavailable`. The licence here is a RULING, not a
derivation, and it is labelled as one (`kind: "design_ruling"`).

The engine's emit-when-empty behaviour for husbandryAnimals/clusters is
UNDOCUMENTED -- `AnimalClusterSystem` has no page in the 1,661-page LUADOC
corpus, and that class is where the write-or-skip decision lives. What IS
documented is only that the path is VALID:
PlaceableHusbandryAnimals.registerSavegameXMLPaths registers ".clusters"
unconditionally. REGISTRATION IS NOT EMISSION -- a registered path declares a
key is legal, never that it is written when its collection is empty. Reading
that registration as an answer is the available mistake here, and this script
does not make it. sec. 6.3.2 rules the case instead, as ARCH-R3-01, and the
`design_ruling` label is what stops a ruling being read as a schema fact.

Corroborating observation (decision-log DEC-051): the three player-owned
husbandries on this save carry zero <husbandryAnimals> and zero <clusters>
nodes while being empty -- consistent with the ruling, though one save cannot
prove the engine's behaviour. The ruling is retired by a live test, not by this
script.

TYPING (sec. 6.5 -- rev 4 rule 5)
---------------------------------
Default is raw, but WHERE A SCHEMA GUARANTEE EXISTS THE COERCION IS MANDATORY,
not merely permitted. All four of age/health/numAnimals/reproduction are
declared g_int -- a restriction of xs:integer -- so all four are int, each with
its own citation.

This is a CHANGE from what this script first shipped, and the reason matters
more than the change. rev 3's rules 1-4 made BOTH answers compliant: rule 1 made
raw the always-available default and rule 2 made int available once cited, so
nothing chose. A rule that permits two answers for one field is taste, which is
the exact decay sec. 6.5 claims to prevent -- and 39 builders reading it
correctly would have produced a spread. The defect was never the typing choice;
it was sec. 6.5 being permissive while calling itself mechanical.

subType stays raw: the XSD declares it g_string and it holds a NAME
("COW_HOLSTEIN") that merely reads like a numeric code.

placeable_id stays raw under rule 5's ONE declared exception -- a field listed
in identity_fields is never coerced. The reason is not typing, it is meaning: an
identifier that happens to be numeric is not a quantity.

A value that fails its declared coercion is an error, never a fallback.

Output contract:
    - Could-not-run -- bad args, unreadable placeables.xml, unknown farm_id --
      emits a top-level {"error": ...} and exits 1 (sec. 6.3, DEC-001). Never [],
      never {}, never None, never a coerced guess.
    - The script ran -- the envelope is emitted with the animal_clusters section
      always present. The section is never suppressed, on any farm, ever.
"""
import hashlib
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

SCHEMA_VERSION = 1
GENERATOR = "read_livestock.py"
GENERATOR_VERSION = "1.0.0"
USAGE = "read_livestock.py <savegame_dir> [--farm-id N]"

DOMAIN = "livestock"
SET = "livestock"
CAPABILITY_IDS = ["b10"]
SECTION = "animal_clusters"

# The five attributes savegame_placeables.xsd:534-557 declares on <animal>.
# All five are required: a missing one is a schema surprise, not a default.
ANIMAL_ATTRS = ("age", "health", "numAnimals", "reproduction", "subType")

# sec. 6.5 rule 5 (rev 4): where a schema guarantee EXISTS, coercion is
# MANDATORY, not merely permitted. All four of age/health/numAnimals/
# reproduction are declared g_int, so all four are int -- typing three of them
# raw while typing numAnimals int on the IDENTICAL guarantee was an internal
# inconsistency inside one worked example.
#
# The one exception, and it must be declared: a field listed in identity_fields
# stays raw however well-typed the schema is. placeable_id is an IDENTIFIER --
# it names a thing, it is not a quantity, and coercing it invites arithmetic
# that is nonsense however lossless the conversion was.
TYPING = {
    "placeable_id": "raw",
    "placeable_name": "raw",
    "age": "int",
    "health": "int",
    "numAnimals": "int",
    "reproduction": "int",
    "subType": "raw",
}

# sec. 6.5 rule 2: every coerced field carries its own citation. No citation =>
# the build fails. Per-field, not a shared string: a blanket citation cannot be
# checked against the attribute it claims to guarantee.
_G_INT = "g_int -> xs:restriction base=xs:integer (savegame_placeables.xsd:50-53)"

TYPING_GUARANTEE = {
    "age": "savegame_placeables.xsd:542 declares @age as " + _G_INT,
    "health": "savegame_placeables.xsd:544 declares @health as " + _G_INT,
    "numAnimals": "savegame_placeables.xsd:546 declares @numAnimals as " + _G_INT,
    "reproduction": "savegame_placeables.xsd:548 declares @reproduction as " + _G_INT,
}

# sec. 7.3 rev 4: a record_list drawn from a per-placeable container MUST carry
# the owning placeable's identity. Without it two clusters in different barns
# are indistinguishable -- harmless for b10, which only counts, but b16/b17 must
# attribute animals to a specific husbandry and would have inherited a lossy
# shape. An identity_fields entry must NOT carry a typing_guarantee: a thing
# cannot be both an identifier and a measured quantity.
IDENTITY_FIELDS = ["placeable_id"]

# Element-level, not file-level (sec. 6.2). Corrected from sec. 7.3's
# `savegame_placeables.xml`, which does not exist -- see the module docstring.
SOURCE_ELEMENTS = ["placeables.xml:placeable/husbandryAnimals/clusters/animal"]

# sec. 6.3.2. Kept verbatim in `kind` and `ruling`: relabelling this as
# `schema_cited` would launder a ruling into a fact, which is the entire point
# of the kind field.
ABSENCE_GUARANTEE_RULED = {
    "kind": "design_ruling",
    "ruling": "ARCH-R3-01",
    "text": (
        "The engine's emit-when-empty behaviour for husbandryAnimals/clusters is "
        "UNDOCUMENTED (sec. 6.3.2). This section reads an absent container as "
        "farm_has_none by ruling, not by derivation."
    ),
    "schema_support": (
        "savegame_placeables.xsd:534-557 declares the element; "
        "PlaceableHusbandryAnimals.registerSavegameXMLPaths registers '.clusters' "
        "unconditionally -- both establish the path is VALID, neither establishes "
        "it is WRITTEN when empty"
    ),
}


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

    BOTH SPELLINGS, AND NOTHING SWALLOWED. This function used to understand only
    the space-separated form and to drop every argument it did not recognise on
    the floor, so `--farm-id=15` selected farm 1 and exited 0 -- a confidently
    reported WRONG FARM, in the script whose own headline warns that 22 of 25
    animal-capable husbandries on this save are map furniture. An unrecognised
    argument is now an error: a caller who misspells a flag is told so, and is
    never handed the default in silence.
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


def read_animal_row(animal_elem, placeable_id, placeable_name):
    """One <animal> -> one typed row, or (None, error_message).

    sec. 6.5 rule 3: a value that fails its declared coercion is an error, never a
    fallback. A missing attribute is likewise an error -- emitting null for it
    would be exactly the absence-as-data mistake DEC-001 exists to prevent.

    The row leads with the owning placeable's identity (sec. 7.3 rev 4). Both id
    and name ship: the id is the stable key b16/b17 must attribute animals by,
    the name is what a human reads. The id is RAW -- it is declared in
    IDENTITY_FIELDS, and rule 5's exception keeps identifiers uncoerced.
    """
    row = {"placeable_id": placeable_id, "placeable_name": placeable_name}
    for attr in ANIMAL_ATTRS:
        raw = animal_elem.attrib.get(attr)
        if raw is None:
            return None, (
                f"<animal> in {placeable_name} has no {attr!r} attribute -- "
                "savegame_placeables.xsd:534-557 declares it. Refusing to "
                "substitute a default for a missing schema attribute."
            )
        if TYPING[attr] == "int":
            try:
                row[attr] = int(raw)
            except ValueError:
                return None, (
                    f"<animal {attr}={raw!r}> in {placeable_name} is not an "
                    "integer, but the XSD declares it g_int. Refusing to coerce "
                    "or drop it."
                )
        else:
            row[attr] = raw
    return row, None


def roll_up(sections):
    """Top-level status/reason -- sec. 6.3.3, rev 4. TOTAL, ORDERED, FIRST MATCH WINS.

        1. ANY section unavailable or partial -> "partial"
        2. EVERY section unknown_by_design    -> "unknown_by_design"
        3. otherwise (>=1 ok, none failed)    -> "ok"

    (Rule 0 -- the script could not run at all -> {"error": ...} + exit 1 -- is
    handled by fail() before any section is built, so it cannot reach here.)

    THIS SCRIPT PREVIOUSLY HARD-CODED "ok". That was rev 3's sec. 6.3 read --
    the top level answers only "could the script run" -- and it is wrong at rev
    4. On this save every section is unknown_by_design, so the domain now
    reports unknown_by_design, which is what sec. 9.1's aggregate was ALREADY
    rendering ("## Livestock  status: unknown_by_design") and what neither
    wave-1 lane produced.

    RULE 1 OUTRANKS RULE 2 DELIBERATELY. A domain that is PARTLY unreadable
    must never report the confident unknown_by_design: that status is a
    positive claim about the farm ("this farm owns no animals"), and a failed
    section means we do not know. sec. 6.3.3 -- the status that claims more
    never wins a tie.

    ⚠ BUT THE ORDER IS UNOBSERVABLE, AND THIS DOCSTRING USED TO CLAIM OTHERWISE.
    It told its reader that swapping these two branches was a mutation the suite
    would catch. That was FALSE and is finding M9. The conditions are disjoint: rule
    2 fires only when EVERY section is unknown_by_design, which means no section
    is unavailable or partial, which is exactly rule 1's condition failing. So
    swapping the branches is a semantic no-op -- measured over all 340 status
    combinations (zero overlaps), and measured again by performing the swap in
    both domain scripts and running both suites: 106 passed, fully green.

    No test can catch a change to this order, because there is no behaviour to
    catch. The sentence mattered anyway: a maintainer reading it would believe a
    guard existed where none can exist, which is the same manufactured
    confidence a test-that-cannot-fail produces, relocated into prose. The
    honest guard is the exhaustive truth table in the b10 suite, whose teeth ARE
    measured -- deleting rule 1, deleting rule 2, or dropping the empty-sections
    guard each turn it red.
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
    # surprise in this file fails loud. This one used to `continue` -- no
    # counter, no partial, no reason -- so farmId="1.0" made a barn holding 120
    # animals vanish and the section then reported count 0 / farm_has_none while
    # CITING ARCH-R3-01 to license it. The ruling licenses reading an ABSENT
    # container as "the farm owns none"; it cannot license data we DROPPED.
    # Dropped is not absent, and presenting one as the other is the DEC-001
    # defect this whole domain exists to prevent.
    if malformed_farm_ids:
        shown = ", ".join(repr(m) for m in sorted(set(malformed_farm_ids))[:5])
        fail(
            f"{len(malformed_farm_ids)} <placeable> element(s) carry a farmId "
            f"that is not an integer ({shown}). Ownership cannot be established "
            "for them, and skipping them in silence would let a populated barn "
            "disappear into a farm_has_none reading. Refusing to drop them.",
            calibration_needed=True,
        )

    if not farms_seen:
        fail(
            "placeables.xml holds <placeable> elements but not one carries a "
            "farmId attribute -- ownership cannot be established, and reporting "
            "an unowned map as this farm's livestock would be worse than failing.",
            calibration_needed=True,
        )

    if farm_id not in farms_seen:
        # Not a farm with no animals -- a farm that is not in this file at all.
        # Reporting farm_has_none here would convert a lookup miss into a claim
        # about a farm we never found.
        fail(
            f"farm_id {farm_id} owns no placeables in placeables.xml. "
            f"Available farm_ids: {sorted(farms_seen)}",
            calibration_needed=False,
        )

    # --- b10: husbandryAnimals/clusters/animal ------------------------------
    #
    # EVERY SIBLING CONTAINER IS READ, NOT THE FIRST. This loop used to call
    # find("husbandryAnimals") and find("clusters"), each of which returns the
    # FIRST match and discards the rest in silence. A fixture with two <clusters>
    # siblings whose second held 42 cows produced count 0, empty_means
    # farm_has_none and exit 0, with a reason asserting "this farm owns no
    # animals... the container was found, so this is an observation, not an
    # inference". It was neither: it was 42 animals dropped on the floor.
    #
    # That is DEC-001's founding defect rebuilt inside the fix for it -- the
    # product exists because a manager once reported a farm owned nothing while
    # it owned 18 parcels. And it rested on precisely the assumption this
    # module's own docstring warns against: AnimalClusterSystem has no page in
    # the LUADOC corpus, so "the engine writes only one container" is UNVERIFIED.
    # Reading every container cannot under-report and needs no such assumption.
    clusters_containers = 0
    husbandry_placeables = 0
    husbandries_without_container = 0
    rows = []
    for placeable in owned:
        animals_elems = placeable.findall("husbandryAnimals")
        if not animals_elems:
            if placeable.find("husbandry") is not None:
                husbandry_placeables += 1
                husbandries_without_container += 1
            continue
        husbandry_placeables += 1
        clusters_elems = [c for a in animals_elems for c in a.findall("clusters")]
        if not clusters_elems:
            husbandries_without_container += 1
            continue
        clusters_containers += len(clusters_elems)
        name = os.path.basename(placeable.attrib.get("filename", "") or "<unnamed>")
        # sec. 7.3 rev 4's row example shows `"placeable_id": "14"`. NO SUCH
        # ATTRIBUTE EXISTS. Measured on the live save: <placeable> carries
        # exactly age/boughtWithFarmlandOverwrite/canBeDeletedOverwrite/farmId/
        # filename/isPreplaced/modName/nameL10nKey/position/price/rotation/
        # uniqueId -- and no bare `id`. savegame_placeables.xsd:1596 declares
        # @uniqueId as g_string, documented "Placeable's unique id", and it is
        # the only placeable-level identity the schema defines.
        #
        # Measured on this save: all 216 placeables carry uniqueId and there
        # are ZERO duplicates, so it satisfies what sec. 7.3 actually requires
        # -- that two clusters in different barns be distinguishable. The
        # spec's "14" is illustrative and not reproducible from the data;
        # reported to team-lead rather than silently invented.
        #
        # g_string also independently confirms `raw`: this id is not merely
        # uncoerced by rule 5's exception, it has no numeric type to coerce to.
        placeable_id = placeable.attrib.get("uniqueId")
        if placeable_id is None:
            fail(
                f"<placeable> {name!r} on farm {farm_id} holds <clusters> but has "
                "no uniqueId attribute -- savegame_placeables.xsd:1596 declares "
                "it, and it is the only placeable identity the schema defines. "
                "Refusing to emit animal rows that cannot be attributed to a "
                "specific husbandry (sec. 7.3).",
                calibration_needed=True,
            )
        for clusters_elem in clusters_elems:
            for animal_elem in clusters_elem.findall("animal"):
                row, row_err = read_animal_row(animal_elem, placeable_id, name)
                if row_err:
                    fail(row_err, calibration_needed=True)
                rows.append(row)

    # THE LICENCE IS OWED WHENEVER ANY CONTAINER IS ABSENT -- not only when ALL
    # of them are, AND NOT ONLY WHEN THE FARM TURNED OUT TO OWN NOTHING. The
    # old branch was `elif clusters_containers:`, which is farm-wide: one barn
    # present-and-empty plus one barn with no container at all took the
    # present-but-empty path, emitted absence_guarantee null where sec. 6.3.1
    # rule 2 REQUIRES a licence, and asserted "an observation, not an
    # inference" -- true of the first barn, false of the second, in one output
    # that cannot tell you which. Mixed state is the common shape on a real farm
    # and it is finding H7.
    #
    # ⛔ THE LICENCE IS DECIDED BY `husbandries_without_container`, NEVER BY
    # `rows`, AND THAT IS THE WHOLE POINT. Guarding it behind `if rows:` fixed
    # H7 only at the depth it was reproduced -- on a farm that owned NOTHING.
    # The instant one barn held animals, `if rows:` won the race and set the
    # licence to null WITHOUT EVER CONSULTING the absent barn, so a farm with
    # one stocked barn and one container-less barn reported
    # `status: ok / absence_guarantee: null` -- a count presented as a complete
    # census when part of it rests on ARCH-R3-01. That is the exact rule the
    # comment above declares, broken by the branch immediately below it.
    #
    # The count is what carries the false claim here: "this farm owns N
    # animals" is only true of the absent barn BY RULING, and a reader auditing
    # rulings must be able to see that from the licence field rather than by
    # re-deriving it from prose. So the licence is computed ONCE, from the
    # condition that actually licenses it, and every branch below reads it.
    licence_owed = bool(husbandries_without_container)
    absence_guarantee = dict(ABSENCE_GUARANTEE_RULED) if licence_owed else None

    if rows:
        # Nothing FAILED -- rows were read and no section is degraded -- so this
        # stays `ok` (sec. 6.3.3 rule 3) and the ruling is declared through the
        # licence, which is what that field exists for. Reporting `partial`
        # instead would claim the domain was partly UNREADABLE, and an absent
        # container is not unreadable: ARCH-R3-01 reads it, as a ruling.
        status = "ok"
        if licence_owed:
            reason = (
                f"farm {farm_id} owns {len(rows)} recorded <animal> row(s), on "
                f"MIXED evidence: {clusters_containers} <clusters> container(s) "
                f"were read directly, while {husbandries_without_container} "
                "further animal-capable husbandry placeable(s) hold no "
                "<clusters> container and are read as empty on ruling ARCH-R3-01 "
                "(sec. 6.3.2). This count is therefore part observation and "
                "part ruling -- it is a complete census of this farm's animals "
                "only if the ruling holds, and the licence is owed for the "
                "absent half."
            )
        else:
            reason = None
    elif husbandries_without_container:
        # sec. 6.3.1 rule 2 + sec. 6.3.2: at least one container is ABSENT, so
        # part of this answer rests on ruling ARCH-R3-01 and the licence is
        # MANDATORY. Whether the rest were present-and-empty changes the prose,
        # never the licence.
        # The licence itself is set ABOVE, from licence_owed -- which this
        # branch's own condition is. Re-assigning it here would restore the
        # second source of truth the fix exists to remove.
        status = "unknown_by_design"
        if clusters_containers:
            reason = (
                f"farm {farm_id} owns no animals, on MIXED evidence: "
                f"{clusters_containers} <clusters> container(s) are present and "
                f"hold no <animal> rows, while {husbandries_without_container} "
                "animal-capable husbandry placeable(s) carry no container at "
                "all. The absent ones are read as farm_has_none on ruling "
                "ARCH-R3-01 (sec. 6.3.2), so this reading is part observation "
                "and part ruling, and the licence is owed for the absent half."
            )
        else:
            reason = (
                f"no <husbandryAnimals>/<clusters> container on any of farm {farm_id}'s "
                f"{husbandry_placeables} animal-capable husbandry placeable(s). The "
                "container is ABSENT, not empty, so this reading rests on ruling "
                "ARCH-R3-01 (sec. 6.3.2) and not on a schema guarantee: the XSD declares "
                "the element but does not establish that the engine writes it when the "
                "herd is empty."
            )
    else:
        # sec. 6.3.1 rule 4: present-but-empty, and now EVERY animal-capable
        # husbandry has a container, so the claim below is true of all of them.
        status = "unknown_by_design"
        reason = (
            f"{clusters_containers} <clusters> container(s) on farm {farm_id} are "
            "present and hold no <animal> rows -- this farm owns no animals. Every "
            "animal-capable husbandry has its container, so this is an observation, "
            "not an inference."
        )

    # Key order follows sec. 6.2's declared envelope, so a reader diffing this
    # against the spec is comparing like with like.
    section = {
        "status": status,
        "reason": reason,
        "shape": "record_list",
        "capability_ids": list(CAPABILITY_IDS),
        "typing": dict(TYPING),
        "typing_guarantee": dict(TYPING_GUARANTEE),
        "identity_fields": list(IDENTITY_FIELDS),
        # A property of what this section MEANS, not of how many rows it found:
        # an empty animal list always means this farm owns no animals.
        "empty_means": "farm_has_none",
        "absence_guarantee": absence_guarantee,
        "source_elements": list(SOURCE_ELEMENTS),
        # farms.xml's blocked fieldPurchase element (BUG-014) is not read
        # here; placeables.xml husbandry paths are not on the block list.
        "blocked_by": None,
        "count": len(rows),
        "data": rows,
    }

    sections = {SECTION: section}
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
