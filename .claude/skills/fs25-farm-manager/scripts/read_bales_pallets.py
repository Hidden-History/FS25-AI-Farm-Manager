"""
DOMAIN SCRIPT (b19, b22, b23, b25) -- bales and pallets, emitted in the sec. 6.2
domain envelope.

Usage: python3 read_bales_pallets.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

Built against architecture-farm-manager-cached-state.md rev 4, following the
template read_livestock.py established and read_productions.py extends.

Reads THREE files, read-only: items.xml, placeables.xml, vehicles.xml. Nothing
here writes to the savegame, ever. The only writes this process performs are to
stdout.

    b19  items.xml     <item className="Bale">           -- loose bales on the ground
    b22  placeables.xml <objectStorage><object className="Bale">
    b23  vehicles.xml  <vehicle><pallet age=> + <fillUnit><unit>
    b25  vehicles.xml  <baler numBales=> + <baleCounter sessionCounter= lifetimeCounter=>

Three files means three provenance sources and one source_set_hash over all of
them (sec. 2.1): this domain is stale if ANY of the three moves.

⛔ className IS A FILTER, NOT A LABEL -- AND SAMPLING HID THAT
--------------------------------------------------------------
Measured on the live save: the one objectStorage on this farm holds 33 <object>
elements -- NINE className="Bale" and TWENTY-FOUR className="Vehicle". Object
storage stores vehicles as well as bales, in the same container, under the same
element name.

The first six children are all bales, so a reader that sampled the head of the
list -- which is exactly what an interactive `head` on the XML shows you -- would
conclude the container holds bales and emit all 33. That reports 24 stored
VEHICLES as bales, a 3.7x overcount, with every row otherwise well-formed. b22 is
"bales in object storage", so className is the filter that makes the section mean
what its name says.

OWNERSHIP, AND THE ONE PLACE THIS DOMAIN FILTERS DIFFERENTLY
-------------------------------------------------------------
b19, b23 and b25 filter on the owning element's own farmId, as every other reader
here does.

b22 is the exception and the reason is in the schema. The bale is an <object>
that carries its OWN farmId, documented "Id of owner farm", nested inside a
<placeable> that carries a DIFFERENT farmId documented as the storage's owner.
Those are two different questions -- who owns the bale, and who owns the shed --
and "what bales does this farm own" is answered by the first. So this section
scans EVERY placeable's object storage and filters on the object's own farmId,
recording the storing placeable's identity and farmId on every row so a
divergence is visible in the data rather than hidden by the filter.

⚠ ON THIS SAVE THE TWO FILTERS AGREE -- 33 of 33 objects have the same farmId as
their placeable, and both readings yield the same 9 bales. So this choice is
UNOBSERVABLE on the live save and is made on the schema's documentation, not on
evidence. Stated rather than quietly assumed: if a future save ever separates
them, this section's answer changes and no test here would have predicted which
way. The suite covers both arrangements with fixtures precisely because the live
save cannot.

ABSENCE OF AN OPTIONAL ATTRIBUTE IS NOT A VALUE -- EXCEPT WHERE THE XSD SAYS SO
--------------------------------------------------------------------------------
Same rule as read_productions.py, and the same evidence: the XSD's own use of
`default=` is the discriminator. Measured on savegame_placeables.xsd's
objectStorage <object> and savegame_items.xsd's <item>:

    isMissionBale         g_bool  default="false"   <- absence IS false, by citation
    defaultFarmProperty   g_bool  default="false"   <- absence IS false, by citation
    baleTypeIndex         g_int   default="1"       <- absence IS 1, by citation
    fillLevel             g_float  (no default)     <- absence is NOT zero
    wrappingState         g_float  (no default)     <- absence is NOT zero
    numBales              g_int    (no default)     <- absence is NOT zero

⚠ THE TWO fillLevel ATTRIBUTES DO NOT AGREE, AND THAT IS NOT A TYPO. A production
storage node's @fillLevel carries default="0" (read_productions.py relies on it);
an objectStorage object's @fillLevel does NOT. Same attribute name, two elements,
two different schema contracts. Inheriting the first rule into the second would
manufacture a zero the schema never promised, so each is cited where it is used.

TYPING, AND THE `bool` BRANCH THAT CANNOT BE TAKEN
----------------------------------------------------
sec. 6.5's hazard table coerces a boolean-as-string to `bool` "only with an XSD
xs:boolean citation; else raw". Measured across all 88 XSDs in this install:

    grep -l 'type="xs:boolean"' shared/xml/schema/*.xsd | wc -l   ->  0
    g_bool is everywhere <xs:restriction base="xs:string"> + pattern true|false

No such citation exists to be made, so isMissionBale and isBigBag ship RAW --
the hazard table's own fallback. No test asserts a bool coercion goes red,
because a test satisfying an unsatisfiable clause cannot fail; the measurement is
asserted instead.

WHAT THIS DOMAIN DOES NOT ANSWER
---------------------------------
b20 (bale capacity/mass/wrappability/fermentation), b21 (the map's available bale
set) and b24 (pallet definitions and capacity) are DEFINITION data in the game
install and the map mod, not in the savegame. This reader opens the savegame
only. So `pallets` below reports what each pallet CARRIES -- the savegame has
that -- and never what it could carry, which it does not.

Output contract:
    - Could-not-run -- bad args, any of the three files unreadable, unknown
      farm_id -- emits a top-level {"error": ...} and exits 1 (sec. 6.3, DEC-001).
      Never [], never {}, never None, never a coerced guess.
    - The script ran -- the envelope is emitted with all four sections always
      present. No section is ever suppressed, on any farm, ever.
"""
import hashlib
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

SCHEMA_VERSION = 1
GENERATOR = "read_bales_pallets.py"
GENERATOR_VERSION = "1.0.0"
USAGE = "read_bales_pallets.py <savegame_dir> [--farm-id N]"

DOMAIN = "bales_pallets"
SET = "production"
CAPABILITY_IDS = ["b19", "b22", "b23", "b25"]

# The three files this domain reads, in the order they are hashed.
SOURCE_FILES = ("items.xml", "placeables.xml", "vehicles.xml")

# sec. 6.5 rule 2: per-field citations. A blanket string cannot be checked
# against the attribute it claims to guarantee.
_G_FLOAT_ITEMS = "g_float -> xs:restriction base=xs:float (savegame_items.xsd:30-33)"
_G_FLOAT_PLACE = "g_float -> xs:restriction base=xs:float (savegame_placeables.xsd:30-33)"
_G_FLOAT_VEH = "g_float -> xs:restriction base=xs:float (savegame_vehicles.xsd:30-33)"
_G_INT_VEH = "g_int -> xs:restriction base=xs:integer (savegame_vehicles.xsd:50-53)"

# The className that makes an object a bale. See the module docstring -- this is
# a filter, and the container holds Vehicles too.
BALE_CLASS = "Bale"


# ⛔ THE SENTINEL, AND WHY A ROW NEVER CARRIES null
#
# `{"age": null}` reads as "this pallet HAS no age". The truth being reported is
# "the file did not carry that attribute". Those are different facts and DEC-001
# exists because this codebase keeps conflating them -- it is the founding defect
# one level in, inside a row instead of inside a section.
#
# So an absent attribute is OMITTED from the row and named in `absent_attributes`.
# A key that is present carries an observed value; a key that is missing was not
# in the file. A consumer doing row["age"] on an absent attribute now gets a
# KeyError, which is loud, instead of None, which is silently indistinguishable
# from a real null.
#
# ONE MECHANISM, NOT PER-FIELD FLAGS. This started as ad-hoc `*_absent` booleans
# on three fields (fill_level, num_bales, unique_id) -- which left `age`,
# `wrapping_state`, `fill_unit_capacity`, `session_counter` and
# `lifetime_counter` emitting bare nulls. Per-field flags are opt-in, and this
# project keeps finding opt-in guards green and toothless. The suite asserts
# NO NULL ANYWHERE INSIDE `data`, so a section added later cannot reintroduce the
# shape without turning it red.
#
# Scoped to `data` deliberately: sec. 6.2 REQUIRES null-valued keys at section
# level (`reason`, `absence_guarantee`, `blocked_by`), so a blanket no-nulls rule
# over the whole envelope would contradict the envelope.
_ABSENT = object()


def build_row(pairs, defaulted=()):
    """(key, value) pairs -> a row with absent values omitted, not nulled.

    `value is _ABSENT` means the source attribute was not present. Every such key
    is dropped and listed in `absent_attributes`, so absence is still reported --
    it is simply reported as absence rather than as a value.
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
    """A raw attribute, or the absent sentinel."""
    return attrib[name] if name in attrib else _ABSENT


def opt_coerced(attrib, name, kind, field, where, citation_file):
    """A coerced attribute, or the absent sentinel. Never a substituted default."""
    if name not in attrib:
        return _ABSENT
    return coerce(attrib[name], kind, field, where, citation_file)


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

    Returns (farm_id, error_or_None). Both spellings, and an unrecognised
    argument is an ERROR rather than being dropped on the floor -- the H3 defect
    read_livestock.py documents. Silently defaulting to farm 1 after a misspelt
    flag reports the wrong farm's property and exits 0.
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
    """sec. 2.1 source record, one per file this domain actually reads."""
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
    scalar per domain -- and with three sources it is what makes "any of them
    moved" a single comparison rather than three."""
    lines = sorted("%s\0%s" % (s["path"], s["sha256"]) for s in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def coerce(raw, kind, field, where, citation_file):
    """Coerce one attribute, or fail loud. sec. 6.5 rule 3: a value that fails its
    declared coercion is an ERROR, never a fallback."""
    if kind == "float":
        try:
            value = float(raw)
        except ValueError:
            fail(
                f"{field}={raw!r} on {where} is not a number, but "
                f"{citation_file} declares it g_float. Refusing to coerce or drop it.",
                calibration_needed=True,
            )
        # NaN/Infinity are Python floats but NOT JSON numbers -- json.dumps emits
        # them bare and no strict reader accepts them. read_farm_ledger.py hit
        # this on the money ledger.
        if value != value or value in (float("inf"), float("-inf")):
            fail(
                f"{field}={raw!r} on {where} coerces to a non-finite float, which "
                "is not a JSON number. Refusing to emit it.",
                calibration_needed=True,
            )
        return value
    try:
        return int(raw)
    except ValueError:
        fail(
            f"{field}={raw!r} on {where} is not an integer, but {citation_file} "
            "declares it g_int. Refusing to coerce or drop it.",
            calibration_needed=True,
        )


def owning_farm_id(element, what, malformed):
    """The element's own farmId as an int, or None if absent/malformed.

    A farmId that will not parse is recorded rather than skipped: dropping it
    silently is how owned property disappears into a 'this farm has none'
    reading, which is the C3 defect one domain over.
    """
    raw = element.attrib.get("farmId")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        malformed.append((what, raw))
        return None


def roll_up(sections):
    """Top-level status/reason -- sec. 6.3.3, rev 4. TOTAL, ORDERED, FIRST MATCH WINS.

        1. ANY section unavailable or partial -> "partial"
        2. EVERY section unknown_by_design    -> "unknown_by_design"
        3. otherwise (>=1 ok, none failed)    -> "ok"

    COPIED, NOT IMPORTED, and deliberately -- extracting it into xml_utils.py
    would breach TECH-DEBT-023. The guard on this copy is this suite's own
    exhaustive truth table, not the other suites'.

    RULE 1 OUTRANKS RULE 2 DELIBERATELY: a partly unreadable domain must never
    reach the confident unknown_by_design, which is a positive claim about the
    farm.

    ⚠ THE ORDER OF RULES 1 AND 2 IS UNOBSERVABLE and no test here claims
    otherwise -- the conditions are disjoint, so swapping the branches is a
    semantic no-op (finding M9). What IS measured: deleting rule 1, deleting rule
    2, and dropping the empty-sections guard each turn this suite red.
    """
    degraded = sorted(name for name, s in sections.items()
                      if s["status"] in ("unavailable", "partial"))
    if degraded:
        return "partial", "section(s) not fully read: " + "; ".join(
            "%s (%s): %s" % (n, sections[n]["status"], sections[n]["reason"])
            for n in degraded)

    # `sections and` guards the vacuous case: all() over an empty dict is True,
    # which would turn a domain that emitted NO sections into the confident claim
    # "this farm has none". A domain with no sections is a bug (sec. 6.4).
    if sections and all(s["status"] == "unknown_by_design" for s in sections.values()):
        return ("unknown_by_design",
                "no data of any kind on this farm for this domain")

    return "ok", None


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        emit({"usage": USAGE, "domain": DOMAIN, "capability_ids": CAPABILITY_IDS})
        return

    savegame_dir = arg_or_exit(USAGE)
    farm_id, arg_err = parse_farm_id_arg(sys.argv)
    if arg_err:
        fail(arg_err, calibration_needed=False)

    # --- Load all three sources up front -------------------------------------
    #
    # A missing file is a could-not-run, not a section-level absence. items.xml
    # holding <items/> is an EMPTY CONTAINER and is a completely different fact
    # from items.xml not existing -- the first says the farm has no loose bales,
    # the second says we could not look. Collapsing them is the DEC-001 error.
    roots = {}
    for name in SOURCE_FILES:
        path = os.path.join(savegame_dir, name)
        root, generic = load_xml(path)
        if root is None:
            fail(
                f"could not read {name}: {generic.get('error')}",
                calibration_needed=True,
            )
        roots[name] = root

    provenance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "sources": [file_provenance(os.path.join(savegame_dir, n))
                    for n in SOURCE_FILES],
    }
    provenance["source_set_hash"] = source_set_hash(provenance["sources"])

    malformed = []

    # --- b19: loose bales on the ground (items.xml) --------------------------
    #
    # `items/item` per savegame_items.xsd:142-148. A loose bale is an <item>
    # whose className is Bale -- the same className filter b22 needs, for the
    # same reason: <item> is the generic on-the-ground object.
    loose = []
    items_total = 0
    # The ordinal carries the same caveat as b22's, and for a reason that cannot
    # be measured away here: this save's items.xml is `<items/>`, so whether the
    # engine writes @uniqueId on a real <item> is UNMEASURED on this machine. The
    # XSD declares it (savegame_items.xsd:222); zero of the 33 analogous
    # objectStorage objects carry it. Assuming it will be present because the
    # schema declares it is exactly the registration-is-not-emission trap
    # ARCH-R3-01 was written about, so this section handles both cases rather
    # than betting on one.
    for ordinal, item in enumerate(roots["items.xml"].findall("item")):
        items_total += 1
        if item.attrib.get("className") != BALE_CLASS:
            continue
        if owning_farm_id(item, "items.xml <item>", malformed) != farm_id:
            continue
        where = "items.xml <item #%d>" % ordinal
        loose.append(build_row([
            ("unique_id", opt(item.attrib, "uniqueId")),
            ("ordinal_in_file", ordinal),
            ("fill_type", opt(item.attrib, "fillType")),
            ("filename", opt(item.attrib, "filename")),
            # No default in savegame_items.xsd, so an absent fillLevel is NOT
            # zero -- the key is omitted rather than nulled or defaulted.
            ("fill_level", opt_coerced(item.attrib, "fillLevel", "float",
                                       "fillLevel", where, "savegame_items.xsd")),
            ("wrapping_state", opt_coerced(item.attrib, "wrappingState", "float",
                                           "wrappingState", where,
                                           "savegame_items.xsd")),
            # default="false" IS declared, so absence is false BY CITATION and
            # this one is a value rather than an absence.
            ("is_mission_bale", item.attrib.get("isMissionBale", "false")),
            # An inline multi-bale item lists its members here.
            ("inline_bale_count",
             sum(len(b.findall("bale")) for b in item.findall("bales"))),
        ], defaulted=[k for k, a in (("is_mission_bale", "isMissionBale"),)
                      if a not in item.attrib]))

    # --- b22: bales in object storage (placeables.xml) -----------------------
    #
    # EVERY placeable is scanned, not only this farm's -- the object carries its
    # own farmId and that is what owns the bale. See the module docstring.
    stored = []
    object_total = 0
    non_bale_objects = 0
    for placeable in roots["placeables.xml"].iter("placeable"):
        p_farm = placeable.attrib.get("farmId")
        p_id = placeable.attrib.get("uniqueId")
        p_name = os.path.basename(
            placeable.attrib.get("filename", "") or "") or "<unnamed>"
        for storage in placeable.findall("objectStorage"):
            # ORDINAL IS POSITION WITHIN THIS CONTAINER, and it exists because
            # the schema's own identity attribute is not written. Measured on the
            # live save: savegame_placeables.xsd:1152 declares @uniqueId on this
            # element, and ZERO of the 33 stored objects carry it. Worse, all
            # nine bales share ONE identical attribute signature -- same fillType,
            # fillLevel, filename, wrapping, everything -- so without a positional
            # key nine rows are mutually indistinguishable and no consumer can
            # address one of them.
            #
            # This is finding N from sec. 7.3 rev 4, in a new element: a
            # record_list drawn from a per-placeable container MUST carry enough
            # identity to tell two rows apart. Emitting `unique_id: null` as an
            # identity field would have declared an identity that does not
            # identify -- absence dressed as a key.
            #
            # ⚠ THE ORDINAL IS NOT STABLE ACROSS SAVES and is not claimed to be.
            # It orders rows within one reading of one file. `unique_id` is still
            # emitted, because the schema declares it and another save or a mod
            # may well write it -- when it is present it is the real identity, and
            # `unique_id_absent` says which case a consumer is looking at.
            for ordinal, obj in enumerate(storage.findall("object")):
                object_total += 1
                if obj.attrib.get("className") != BALE_CLASS:
                    non_bale_objects += 1
                    continue
                if owning_farm_id(
                        obj, "placeables.xml <objectStorage><object>",
                        malformed) != farm_id:
                    continue
                where = "objectStorage <object #%d in %s>" % (ordinal, p_id or "?")
                stored.append(build_row([
                    ("unique_id", opt(obj.attrib, "uniqueId")),
                    ("ordinal_in_storage", ordinal),
                    # The shed, kept beside the bale so a divergence between the
                    # two owners is visible in the row rather than hidden by the
                    # filter that selected it.
                    ("storage_placeable_id",
                     p_id if p_id is not None else _ABSENT),
                    ("storage_placeable_name", p_name),
                    ("storage_placeable_farm_id",
                     p_farm if p_farm is not None else _ABSENT),
                    ("fill_type", opt(obj.attrib, "fillType")),
                    ("filename", opt(obj.attrib, "filename")),
                    # ⚠ NO default on THIS element's fillLevel, unlike the
                    # production-storage node's. Absence is not zero here.
                    ("fill_level", opt_coerced(obj.attrib, "fillLevel", "float",
                                               "fillLevel", where,
                                               "savegame_placeables.xsd")),
                    ("wrapping_state", opt_coerced(obj.attrib, "wrappingState",
                                                   "float", "wrappingState",
                                                   where,
                                                   "savegame_placeables.xsd")),
                    ("wrapping_color", opt(obj.attrib, "wrappingColor")),
                    ("is_mission_bale",
                     obj.attrib.get("isMissionBale", "false")),
                    ("is_big_bag", opt(obj.attrib, "isBigBag")),
                ], defaulted=[k for k, a in (("is_mission_bale", "isMissionBale"),)
                              if a not in obj.attrib]))

    # --- b23: pallets in the fleet (vehicles.xml) ----------------------------
    #
    # read_placeables.py aggregates object storage by fillType and read_vehicles.py
    # counts pallets as vehicles; neither says "this is a pallet and it holds X".
    pallets = []
    for vehicle in roots["vehicles.xml"].iter("vehicle"):
        pallet_elems = vehicle.findall("pallet")
        if not pallet_elems:
            continue
        if owning_farm_id(vehicle, "vehicles.xml <vehicle>", malformed) != farm_id:
            continue
        v_id = vehicle.attrib.get("uniqueId")
        where = "vehicles.xml <vehicle %s>" % (v_id or "?")
        contents = []
        for unit_holder in vehicle.findall("fillUnit"):
            for unit in unit_holder.findall("unit"):
                contents.append(build_row([
                    ("index", opt(unit.attrib, "index")),
                    ("fill_type", opt(unit.attrib, "fillType")),
                    ("fill_level", opt_coerced(unit.attrib, "fillLevel", "float",
                                               "fillLevel", where,
                                               "savegame_vehicles.xsd")),
                ]))
        for pallet in pallet_elems:
            pallets.append(build_row([
                ("vehicle_id", v_id if v_id is not None else _ABSENT),
                ("filename", opt(vehicle.attrib, "filename")),
                ("age", opt_coerced(pallet.attrib, "age", "float", "pallet/@age",
                                    where, "savegame_vehicles.xsd")),
                ("contents", contents),
                ("content_count", len(contents)),
            ]))

    # --- b25: baler and bale-counter state (vehicles.xml) --------------------
    balers = []
    for vehicle in roots["vehicles.xml"].iter("vehicle"):
        baler_elems = vehicle.findall("baler")
        counter_elems = vehicle.findall("baleCounter")
        if not baler_elems and not counter_elems:
            continue
        if owning_farm_id(vehicle, "vehicles.xml <vehicle>", malformed) != farm_id:
            continue
        v_id = vehicle.attrib.get("uniqueId")
        where = "vehicles.xml <vehicle %s>" % (v_id or "?")
        # Collected as sentinels first, so a field no <baler>/<baleCounter>
        # supplied stays ABSENT rather than becoming a null the row asserts.
        values = {key: _ABSENT for key in (
            "num_bales", "fill_unit_capacity", "bale_type_index",
            "session_counter", "lifetime_counter")}
        baler_defaulted = []
        for baler in baler_elems:
            if "baleTypeIndex" not in baler.attrib:
                baler_defaulted.append("bale_type_index")
            values["num_bales"] = opt_coerced(
                baler.attrib, "numBales", "int", "numBales", where,
                "savegame_vehicles.xsd")
            values["fill_unit_capacity"] = opt_coerced(
                baler.attrib, "fillUnitCapacity", "float", "fillUnitCapacity",
                where, "savegame_vehicles.xsd")
            # default="1" IS declared on this one, so absence IS 1 by citation --
            # a value, not an absence, and the one field here that is defaulted.
            values["bale_type_index"] = coerce(
                baler.attrib.get("baleTypeIndex", "1"), "int", "baleTypeIndex",
                where, "savegame_vehicles.xsd")
        for counter in counter_elems:
            for key, attr in (("session_counter", "sessionCounter"),
                              ("lifetime_counter", "lifetimeCounter")):
                values[key] = opt_coerced(counter.attrib, attr, "int", attr,
                                          where, "savegame_vehicles.xsd")
        balers.append(build_row(
            [("vehicle_id", v_id if v_id is not None else _ABSENT),
             ("filename", opt(vehicle.attrib, "filename"))]
            + [(key, values[key]) for key in (
                "num_bales", "fill_unit_capacity", "bale_type_index",
                "session_counter", "lifetime_counter")],
            defaulted=baler_defaulted))

    if malformed:
        shown = ", ".join("%s farmId=%r" % (w, r) for w, r in malformed[:5])
        fail(
            f"{len(malformed)} element(s) carry a farmId that is not an integer "
            f"({shown}). Ownership cannot be established for them, and skipping "
            "them in silence would let owned bales or pallets disappear into a "
            "'this farm has none' reading. Refusing to drop them.",
            calibration_needed=True,
        )

    sections = {}

    # ---- b19 ----------------------------------------------------------------
    if loose:
        b19_status, b19_reason = "ok", None
    else:
        # items.xml PARSED and its root element is present. The container is
        # right there and holds nothing -- sec. 6.3.1 rule 4, present-but-empty,
        # which needs NO licence. This is the opposite of b10's absent container.
        # A MISSING items.xml never reaches here: it is a could-not-run above.
        b19_status = "unknown_by_design"
        b19_reason = (
            f"items.xml is present and holds {items_total} <item> element(s), of "
            f"which none is a className={BALE_CLASS!r} owned by farm {farm_id} -- "
            "this farm has no loose bales lying on the ground. The container was "
            "read directly and is empty of matching items, so this is an "
            "observation, not an inference, and no absence licence is owed."
        )
    sections["loose_bales"] = {
        "status": b19_status,
        "reason": b19_reason,
        "shape": "record_list",
        "capability_ids": ["b19"],
        "typing": {
            "unique_id": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
            "ordinal_in_file": "int",
            "fill_type": "raw",
            "filename": "raw",
            "fill_level": "float",
            "wrapping_state": "float",
            "is_mission_bale": "raw",
            "inline_bale_count": "int",
        },
        "typing_guarantee": {
            "fill_level": "savegame_items.xsd:186 declares @fillLevel as "
                          + _G_FLOAT_ITEMS + " (NO default -- absence is not zero)",
            "wrapping_state": "savegame_items.xsd:191 declares @wrappingState as "
                              + _G_FLOAT_ITEMS,
            "inline_bale_count":
                "a cardinality this script computes over "
                "savegame_items.xsd:151 <bale> elements, not a source attribute",
            "ordinal_in_file":
                "a position this script assigns within items.xml, not a source "
                "attribute. NOT stable across saves",
        },
        # Position is the identity that is always available. unique_id is emitted
        # and is the real identity WHEN PRESENT, but this save cannot establish
        # that it ever is -- items.xml is `<items/>` -- so it is not declared as
        # the identity. `unique_id_absent` tells a consumer which case it has.
        "identity_fields": ["ordinal_in_file"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": ["items.xml:items/item"],
        "blocked_by": None,
        "count": len(loose),
        "data": loose,
    }

    # ---- b22 ----------------------------------------------------------------
    if stored:
        b22_status = "ok"
        b22_reason = (
            f"{len(stored)} bale(s) owned by farm {farm_id}, selected by "
            f"className={BALE_CLASS!r} from {object_total} stored object(s); "
            f"{non_bale_objects} object(s) in the same containers are NOT bales "
            "and are excluded. Object storage holds vehicles alongside bales "
            "under the same element name."
        ) if non_bale_objects else None
    elif object_total:
        b22_status = "unknown_by_design"
        b22_reason = (
            f"{object_total} object(s) are present in object storage and none is "
            f"a className={BALE_CLASS!r} owned by farm {farm_id} -- this farm has "
            "no bales in object storage. The containers were read directly, so "
            "this is an observation, not an inference."
        )
    else:
        b22_status = "unknown_by_design"
        b22_reason = (
            "no <objectStorage> holds any <object> anywhere in placeables.xml -- "
            "there is no stored object of any kind on this map, so this farm has "
            "no stored bales."
        )
    sections["object_storage_bales"] = {
        "status": b22_status,
        "reason": b22_reason,
        "shape": "record_list",
        "capability_ids": ["b22"],
        "typing": {
            "unique_id": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
            "ordinal_in_storage": "int",
            "storage_placeable_id": "raw",
            "storage_placeable_name": "raw",
            "storage_placeable_farm_id": "raw",
            "fill_type": "raw",
            "filename": "raw",
            "fill_level": "float",
            "wrapping_state": "float",
            "wrapping_color": "raw",
            "is_mission_bale": "raw",
            "is_big_bag": "raw",
        },
        "typing_guarantee": {
            "fill_level":
                "savegame_placeables.xsd:1133 declares objectStorage/object"
                "/@fillLevel as " + _G_FLOAT_PLACE + " with NO default -- unlike "
                "productionPoint/storage/node/@fillLevel, which has default=\"0\"",
            "wrapping_state":
                "savegame_placeables.xsd:1160 declares @wrappingState as "
                + _G_FLOAT_PLACE,
            "ordinal_in_storage":
                "a position this script assigns within one <objectStorage>, not "
                "a source attribute -- see the comment at the emit site. It is "
                "NOT stable across saves",
        },
        # unique_id is NOT here: savegame_placeables.xsd:1152 declares it but
        # zero objects on this save carry it, and an identity field that is
        # always null does not identify. Position within the container plus the
        # container's own id is what actually tells two rows apart here.
        "identity_fields": ["storage_placeable_id", "ordinal_in_storage"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": ["placeables.xml:placeable/objectStorage/object"],
        "blocked_by": None,
        "count": len(stored),
        "data": stored,
    }

    # ---- b23 ----------------------------------------------------------------
    if pallets:
        b23_status, b23_reason = "ok", None
    else:
        b23_status = "unknown_by_design"
        b23_reason = (
            f"no <vehicle> owned by farm {farm_id} carries a <pallet> element in "
            "vehicles.xml -- this farm owns no pallets. vehicles.xml was read in "
            "full, so this is an observation about a present file, not an "
            "inference from an absent one."
        )
    sections["pallets"] = {
        "status": b23_status,
        "reason": b23_reason,
        "shape": "record_list",
        "capability_ids": ["b23"],
        "typing": {
            "vehicle_id": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
            "filename": "raw",
            "age": "float",
            "contents": "raw",
            "content_count": "int",
        },
        "typing_guarantee": {
            "age": "savegame_vehicles.xsd:1558 declares pallet/@age as "
                   + _G_FLOAT_VEH + ' ("Random age of the pallet [0-1]")',
            "content_count":
                "a cardinality this script computes over <fillUnit><unit> "
                "elements, not a source attribute",
        },
        "identity_fields": ["vehicle_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "vehicles.xml:vehicles/vehicle/pallet",
            "vehicles.xml:vehicles/vehicle/fillUnit/unit",
        ],
        "blocked_by": None,
        "count": len(pallets),
        "data": pallets,
    }

    # ---- b25 ----------------------------------------------------------------
    if balers:
        b25_status, b25_reason = "ok", None
    else:
        b25_status = "unknown_by_design"
        b25_reason = (
            f"no <vehicle> owned by farm {farm_id} carries a <baler> or "
            "<baleCounter> element -- this farm owns no baler. vehicles.xml was "
            "read in full, so this is an observation, not an inference."
        )
    sections["baler_state"] = {
        "status": b25_status,
        "reason": b25_reason,
        "shape": "record_list",
        "capability_ids": ["b25"],
        "typing": {
            "vehicle_id": "raw",
            "absent_attributes": "raw",
            "defaulted_attributes": "raw",
            "filename": "raw",
            "num_bales": "int",
            "fill_unit_capacity": "float",
            "bale_type_index": "int",
            "session_counter": "int",
            "lifetime_counter": "int",
        },
        "typing_guarantee": {
            "num_bales": "savegame_vehicles.xsd:1112 declares @numBales as "
                         + _G_INT_VEH + " (NO default -- absence is not zero)",
            "fill_unit_capacity":
                "savegame_vehicles.xsd:1109 declares @fillUnitCapacity as "
                + _G_FLOAT_VEH,
            "bale_type_index":
                "savegame_vehicles.xsd:1103 declares @baleTypeIndex as "
                + _G_INT_VEH + ' with default="1", so an absent attribute IS 1 '
                "by citation",
            "session_counter":
                "savegame_vehicles.xsd:989 declares @sessionCounter as " + _G_INT_VEH,
            "lifetime_counter":
                "savegame_vehicles.xsd:986 declares @lifetimeCounter as " + _G_INT_VEH,
        },
        "identity_fields": ["vehicle_id"],
        "empty_means": "farm_has_none",
        "absence_guarantee": None,
        "source_elements": [
            "vehicles.xml:vehicles/vehicle/baler",
            "vehicles.xml:vehicles/vehicle/baleCounter",
        ],
        "blocked_by": None,
        "count": len(balers),
        "data": balers,
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
