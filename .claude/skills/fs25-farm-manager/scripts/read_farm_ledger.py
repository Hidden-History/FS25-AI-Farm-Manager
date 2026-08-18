"""
b39 + b40 -- one farm's finance ledger and lifetime counters, emitted in the
§ 6.2 domain envelope.

Usage: python3 read_farm_ledger.py <savegame_dir> [--farm-id N]
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

Spec: _bmad-output/planning-artifacts/architecture-farm-manager-cached-state.md
rev 3 (sha256 5b84029ec28b176697a6cb3e399791be0ecfaeb35f76b4ad19fdbf3cd9832d51).
This script WAS a shape probe with a deliberately provisional output shape,
built ahead of DEC-046 so the format ruling could be made against real output.
The ruling landed and the template now exists, so the probe's shape is gone:
what this emits is the § 6.2 envelope, and § 7.1 / § 7.2 are its worked
examples. The old shape is not a precedent and no longer ships.

Reads ONE file, read-only: farms.xml. Nothing here writes to the savegame, ever.
The only file handles opened are xml_utils.load_xml's parse and this module's
'rb' hash read for provenance (§ 2.1); both are read modes.

    b39  <farm><finances><stats day="0">   -- 33 child elements, one per money
         category, five <stats> blocks (day 0..4). The direct answer to
         "where is the money going".  shape: day_series, coerced to float.
    b40  <farm><statistics>                -- lifetime counters, one child
         element each. The inventory row says "50+"; this save has 47. The
         script reports what it finds and never pads to a claimed count.
         shape: record, every value raw.

Both are CHILD ELEMENTS carrying text, not attributes. The only attribute in
play is <stats day="N">.

⛔ BUG-014 -- WHY THIS SCRIPT CARRIES A blocked_by DECLARATION
-------------------------------------------------------------
⚠ RE-KEYED FROM BUG-012 -- DEC-057 ⑥, and it is not a labelling nit. BUG-012 is
a defect in a SENTENCE (farm_snapshot.py emits a note asserting a match beside a
flag reporting false); it is real, HIGH, and it BLOCKS NOTHING. BUG-014 is the
record with the authority to stop work. The shorthand "land is blocked on
BUG-012" travelled across three sessions and pointed every auditor at the wrong
record.

One of b39's 33 categories is `fieldPurchase`, and slot 0's value IS the figure
BUG-014 is about (read_farmland_areas.py calls it `farms_xml_fieldPurchase_abs`;
that name is its own invention and appears nowhere in the savegame). That script
reads slot 0 ALONE via ElementTree.find and ships it under a name promising a
lifetime absolute -- it answers a question nothing asked.

⚠ THE ORIGINAL PREMISE HERE WAS FALSE AND IS RETIRED. This paragraph used to say
the five-slot sum "reconstructs the other CONTRADICTED figure". The figures never
contradicted: the sum of the five slots is 39,432,192.00, which equals
computed_owned_total_cost to the cent (re-measured, rev 6). There is one land
value and one cash-flow spend total -- two questions, not two answers. So:

  - finance_ledger's source_elements intersect the registry's
    blocked_source_elements, which makes a `blocked_by` declaration MANDATORY
    (§ 6.8.2 tooth 1). Reading a blocked element silently fails the build --
    that is the design, not paperwork.
  - The per-slot rows are correct and MUST ship. b39's whole value is "where is
    the money going", and land purchases are part of that answer. Blocking the
    category outright would break a healthy capability to contain a read defect
    that does not live in it.
  - NOTHING is aggregated. No total, no cumulative, no mean, no abs, no
    cross-check against land area (§ 6.8.2 tooth 3). `count` and
    `category_count` are cardinalities, not money figures, and are exempt.

The block is on PROVENANCE, not on field names and not on values -- so it
survives renaming and arithmetic, and it narrows to nothing with a registry
edit when BUG-014 closes. No block is hard-coded into the reading logic here.

WHY THE TWO SECTIONS ARE TYPED DIFFERENTLY (§ 6.5 / DEC-047)
------------------------------------------------------------
finance_ledger values are homogeneous: 33 money amounts, all written in the
canonical "-883200.000000" form. They are parsed to float, because arithmetic on
them is the entire point of the capability, and the coercion carries a
typing_guarantee. A value that does not parse is a schema surprise and is
reported as an error, never coerced (§ 6.5 rule 3).

lifetime_statistics values are NOT homogeneous. They mix floats
(workedHectares="1019.038208"), integers (baleCount="13") and at least one
zero-padded BITFIELD: treeTypesCut="000000". Coercing that bitfield to a number
yields 0, and a reader would conclude "no tree types were cut" while
cutTreeCount="5" says five trees were felled -- a plausible, wrong answer of
exactly the class this project keeps being bitten by. No schema guarantees a
lossless coercion, so DEC-047's default applies and every value ships as the
file's RAW TEXT, verbatim.

STATE, NOT PROCESS
------------------
The savegame holds no history. The <stats day="N"> blocks are five rolling
slots; this file does NOT establish which calendar day each slot refers to (this
save is on in-game day 10 and the slots are still numbered 0..4). So the raw
`day` attribute is reported as-is and NO rate, trend, burn-down, or "days until"
figure is computed from it. Those live in the delta log (§ 8), which accumulates
across snapshots. Computing one here would also be a tooth-3 violation.

UNITS
-----
farms.xml labels no units. This script therefore converts nothing. Of the
counters here only playTime is established by project convention (minutes --
1561.564941 = ~26 h, consistent with a day-10 save that has worked 1019 ha).
The units of workedTime/cultivatedTime/sownTime/..., traveledDistance,
tractorDistance, fuelUsage, seedUsage and sprayUsage are NOT established, and
guessing at them here is how a wrong number gets published. Raw text only.

OUTPUT CONTRACT -- two levels, and the boundary is precise (§ 6.3)
------------------------------------------------------------------
TOP LEVEL, the script could not run at all -- bad args, unreadable/absent/
malformed farms.xml, no <farm> elements, an unknown --farm-id, or a money value
that fails its declared coercion. These emit {"error": "..."} and EXIT 1
(DEC-001). Never [], {}, None, or a coerced guess.

SECTION LEVEL, the script ran and one section's source is missing or empty:
  - container ABSENT and no schema licenses that absence -> status "unavailable"
    + reason naming the missing element. This is the DEFAULT for an absent
    container (§ 6.3.1 rule 1): absence is not evidence until something says it
    is. No absence_guarantee exists for farms.xml's <finances> or <statistics>,
    so "unknown_by_design" is NOT reachable for an absent container here.
  - container PRESENT but holding nothing -> status "unknown_by_design" +
    empty_means "farm_has_none", count 0, absence_guarantee null. Nothing is
    being inferred -- the container is right there and it is empty -- so nothing
    needs licensing (§ 6.3.1 rule 4).
Every declared section is emitted on every run, always. A missing section is a
bug, never "none" (§ 6.4).

INTERPRETATIONS MADE WHERE rev 3 IS SILENT -- reported, not silently absorbed
-----------------------------------------------------------------------------
  (a) RESOLVED BY rev 4 § 6.3.3 -- no longer an interpretation. rev 3 did not
      specify the top-level derivation, and this script's own rule ("any
      unavailable/partial -> partial, else ok") was MISSING rev 4's rule 2:
      every section unknown_by_design -> top-level unknown_by_design. See
      roll_up(). Recorded rather than deleted, because the divergence this
      silence produced across two lanes is why § 6.3.3 exists.
  (b) count/data for an "unavailable" section are not specified. Used: count 0
      and the shape's empty container ([] for day_series, {} for record), with
      empty_means null -- an unavailable section claims nothing about the farm.
  (c) source_set_hash's line separator is not specified. Used: sorted
      "path\\0sha256" lines joined with "\\n", hashed as UTF-8.
"""
import hashlib
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit

SCHEMA_VERSION = 1
GENERATOR = "read_farm_ledger.py"
GENERATOR_VERSION = "2.0.0"
USAGE = "read_farm_ledger.py <savegame_dir> [--farm-id N]"
DOMAIN = "farm_ledger"
SET = "economy"

# § 6.2 rev 4, ruled 2026-08-02 (errata ④ against the rev-4 spec): every section
# declares identity_fields, and a domain with no per-row identity declares it
# EXPLICITLY -- never by omission. Absence must not be how a field is expressed.
#
# Both of this script's sections declare []. b40 is a `record`: one flat dict of
# lifetime counters with no rows to identify at all. b39 is a `day_series` whose
# rows carry `day`, and `day` is deliberately NOT claimed as an identity field:
# § 7.3's identity rule is about attributing rows to the OWNING ENTITY they were
# drawn from (b10's placeable), and a b39 row is not drawn from a per-entity
# container -- `day` is a rolling slot index this file cannot map to a calendar
# day, reported verbatim and never interpreted. Declaring it an identity would
# additionally force it raw under § 6.5 rule 5's exception, changing shipped
# data no finding asked for. Flagged to team-lead as the one judgement call
# errata ④ leaves open.
IDENTITY_FIELDS_NONE = []

# § 6.8 rev 4 -- THE SECTION CARRIES A KEY, NEVER THE PROSE.
#
# This script used to define PERMITTED_USE_B39, a paraphrase of the registry's
# permitted_uses["b39"] text, and emit it inline. That is exactly the drift
# § 6.8 struck: the two wordings had ALREADY diverged, which is what a copy
# does and a key cannot. DEC-048 (1) turned on the spec's own artifacts -- the
# authored half may REFERENCE a generated value, never repeat it.
#
# The registry is the single authority for the permission text. This script
# names the permission; it does not restate it.
PERMITTED_USE_REF_B39 = "b39"

TYPING_GUARANTEE_B39 = (
    "all 33 children are money amounts in canonical -883200.000000 form; a "
    "non-numeric value is a schema surprise and errors rather than coercing"
)

TYPING_GUARANTEE_B40 = (
    "MIXED -- floats, ints and at least one zero-padded bitfield "
    "(treeTypesCut=\"000000\"). No schema guarantee of lossless numeric "
    "coercion exists, so DEC-047's default applies: raw."
)


def fail(message, calibration_needed):
    """Top-level could-not-run: {"error": ...} on stdout, exit 1. DEC-001.

    Every call site passes a distinct message, deliberately: byte-identical
    error emissions in one file defeat first-occurrence mutation testing and
    have already produced two false "no teeth" verdicts in this codebase
    (TECH-DEBT-021 item 1).
    """
    emit({"error": message, "calibration_needed": calibration_needed})
    sys.exit(1)


def parse_farm_id_arg(argv):
    """Pull --farm-id N (or --farm-id=N) out of argv; default 1.

    Returns (farm_id, error_or_None).

    BOTH SPELLINGS, AND NOTHING SWALLOWED. This function used to understand only
    the space-separated form and to drop every unrecognised argument silently,
    so `--farm-id=15` reported farm 1 and exited 0. The identical defect sat in
    read_livestock.py's copy of this function; fixing one and not the other
    would have rebuilt finding M1 in miniature -- one template, two behaviours,
    each green against its own suite -- so both were fixed in one pass.
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
    """§ 2.1 per-source record. Opened 'rb' -- a read mode, never a write."""
    stat = os.stat(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": path,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": digest.hexdigest(),
    }


def build_provenance(farm_id, sources):
    """§ 2.1. A domain hashes only the files it reads, never the whole savegame:
    freshness is honestly relative to a domain's OWN sources. source_set_hash --
    not generated_at -- is what decides currency, because a save restored from
    backup carries an old mtime and different content."""
    lines = sorted("%s\0%s" % (s["path"], s["sha256"]) for s in sources)
    set_hash = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "sources": sources,
        "source_set_hash": "sha256:" + set_hash,
    }


def section(status, reason, shape, capability_ids, typing, typing_guarantee,
            identity_fields, empty_means, absence_guarantee, source_elements,
            blocked_by, count, data):
    """Build one § 6.2 section. Every key is REQUIRED and is written here
    unconditionally -- only the VALUES are optional. A missing key is a build
    failure, not a default, because defaulting is how a guard gets silently
    skipped: tooth 1 can only detect an undeclared read of a blocked element if
    declaration is universal.

    identity_fields JOINED THAT LIST ON 2026-08-02 (errata ④). § 6.2 declared it
    and §§ 7.1/7.2's worked examples omitted it, so this script -- built from
    those examples -- emitted a 12-key section while read_livestock.py, built
    from § 6.2, emitted 13. Two scripts, one template, two envelopes, and each
    suite validated against its own private key list: the b39/b40 suite tested a
    SUBSET (extras invisible) and the b10 suite tested EXACT equality. One junk
    key injected into every section left this suite 50-passed green and reddened
    livestock. That asymmetry is finding M1 and it ends here: the key is
    written unconditionally, and both suites now assert exact equality against
    one shared key set.

    Key order follows § 6.2's declared envelope, so a reader diffing this
    against the spec -- or against read_livestock.py -- compares like with like.
    """
    return {
        "status": status,
        "reason": reason,
        "shape": shape,
        "capability_ids": capability_ids,
        "typing": typing,
        "typing_guarantee": typing_guarantee,
        "identity_fields": identity_fields,
        "empty_means": empty_means,
        "absence_guarantee": absence_guarantee,
        "source_elements": source_elements,
        "blocked_by": blocked_by,
        "count": count,
        "data": data,
    }


def build_finance_ledger(target, farm_id):
    """b39 -- day_series, 33 float categories per slot. Calls fail() on a schema
    surprise (§ 6.5 rule 3: a value that fails its declared coercion is an
    error, never a fallback)."""
    common = dict(
        shape="day_series",
        capability_ids=["b39"],
        typing={"*": "float"},
        typing_guarantee={"*": TYPING_GUARANTEE_B39},
        identity_fields=list(IDENTITY_FIELDS_NONE),
        # No schema licenses reading an absent <finances> as "the farm has
        # none", so this stays null and unknown_by_design is unreachable for
        # the absent case (§ 6.3.1 rules 1 and 3).
        absence_guarantee=None,
        source_elements=["farms.xml:farm/finances/stats/*"],
        # MANDATORY: source_elements intersect blocked_source_elements.
        # § 6.8.2 tooth 1's intersection is glob-aware and BIDIRECTIONAL, so
        # this section's broad "farms.xml:farm/finances/stats/*" does match the
        # registry's specific ".../fieldPurchase" and the declaration is owed.
        blocked_by={"bug": "BUG-014", "permitted_use_ref": PERMITTED_USE_REF_B39},
    )

    # EVERY SIBLING IS ACCOUNTED FOR, NOT JUST THE FIRST. find() returns the
    # first match and drops the rest in silence: a farm carrying two <finances>
    # elements whose SECOND held the real <stats> blocks reported
    # unknown_by_design / farm_has_none / count 0 -- "this farm has no recorded
    # finance days" about a farm whose ledger was sitting right there. Same
    # class as the <clusters> defect in read_livestock.py (finding C2).
    #
    # Unlike <clusters>, which is a row container whose contents simply UNION,
    # <finances> is a singular record container: merging two of them is
    # undefined and picking one is the dropping defect wearing a different hat.
    # So this fails loud, consistent with every other schema surprise in this
    # file. Never silently drop a sibling -- that is the invariant; whether the
    # honest response is "read them all" or "refuse" depends on whether the
    # union is defined.
    finances_elems = target.findall("finances")
    if len(finances_elems) > 1:
        fail(f"farm_id {farm_id} carries {len(finances_elems)} <finances> "
             "elements. find() returned the first and discarded the rest, so a "
             "populated ledger in a later sibling would be reported as a farm "
             "with no finance history. Refusing to merge two ledgers or to "
             "choose between them.", True)
    finances_elem = finances_elems[0] if finances_elems else None
    if finances_elem is None:
        return section(
            status="unavailable",
            reason=(f"farm_id {farm_id} has no <finances> element in farms.xml -- the "
                    "container itself is absent, which is a schema question, not an "
                    "empty farm. No schema guarantees <finances> is written when a farm "
                    "has no finance history, so this absence carries no information and "
                    "is NOT reported as an empty ledger."),
            empty_means=None,
            count=0,
            data=[],
            **common,
        )

    ledger = []
    for stats_elem in finances_elem.findall("stats"):
        raw_day = stats_elem.attrib.get("day")
        if raw_day is None:
            fail("a <stats> block under <finances> has no 'day' attribute -- "
                 "schema may have changed.", True)
        try:
            day = int(raw_day)
        except ValueError:
            fail(f"<stats day={raw_day!r}> is not an integer -- schema may have changed.",
                 True)

        categories = {}
        for cat_elem in stats_elem:
            raw = (cat_elem.text or "").strip()
            try:
                value = float(raw)
            except ValueError:
                fail(f"finance category <{cat_elem.tag}> in <stats day=\"{day}\"> holds "
                     f"{raw!r}, which is not a number. These are money amounts; "
                     "refusing to coerce or drop it.", True)
            # float() ACCEPTS "NaN" AND "Infinity" -- only ValueError was caught,
            # so both shipped under status: ok. Neither is a JSON number: a
            # strict parser rejects the whole document, and `jq` rewrites NaN to
            # **null**, turning a money figure into absence-as-data in the one
            # section that carries the BUG-014 declaration. Finding H4.
            if not math.isfinite(value):
                fail(f"finance category <{cat_elem.tag}> in <stats day=\"{day}\"> holds "
                     f"{raw!r}, which parses to the non-finite float {value!r}. JSON "
                     "has no NaN or Infinity: strict readers reject the document and "
                     "jq rewrites NaN to null, so emitting it would publish a money "
                     "amount that downstream reads as absent. Refusing to emit it.",
                     True)
            categories[cat_elem.tag] = value
        ledger.append({
            "day": day,
            "category_count": len(categories),
            "categories": categories,
        })

    if not ledger:
        return section(
            status="unknown_by_design",
            reason=("<finances> is present but holds no <stats> blocks -- this farm has "
                    "no recorded finance days. The container is right there and it is "
                    "empty, so nothing is being inferred and no absence licence is owed."),
            empty_means="farm_has_none",
            count=0,
            data=[],
            **common,
        )

    return section(
        status="ok",
        reason=None,
        empty_means=None,
        count=len(ledger),
        data=ledger,
        **common,
    )


def build_lifetime_statistics(target, farm_id):
    """b40 -- record, every counter raw. Reads farms.xml, the same FILE as b39,
    but farm/statistics/* does not intersect blocked_source_elements, so
    blocked_by is null and no declaration is owed. That is the § 6.2
    element-versus-file distinction earning its keep: a file-level block would
    have caught this healthy capability in BUG-014's net for no reason."""
    common = dict(
        shape="record",
        capability_ids=["b40"],
        typing={"*": "raw"},
        typing_guarantee={"*": TYPING_GUARANTEE_B40},
        identity_fields=list(IDENTITY_FIELDS_NONE),
        absence_guarantee=None,
        source_elements=["farms.xml:farm/statistics/*"],
        blocked_by=None,
    )

    # EVERY SIBLING, NOT THE FIRST -- see build_finance_ledger for the class.
    statistics_elems = target.findall("statistics")
    if len(statistics_elems) > 1:
        fail(f"farm_id {farm_id} carries {len(statistics_elems)} <statistics> "
             "elements. find() returned the first and discarded the rest, so a "
             "populated counter set sitting in the second one would report as "
             "'this farm has recorded nothing yet'. Refusing to merge two "
             "counter records or to pick one of them.", True)
    statistics_elem = statistics_elems[0] if statistics_elems else None
    if statistics_elem is None:
        return section(
            status="unavailable",
            reason=(f"farm_id {farm_id} has no <statistics> element in farms.xml -- the "
                    "container itself is absent, which is a schema question, not a farm "
                    "with no history. No schema guarantees <statistics> is written when "
                    "a farm has recorded nothing, so this absence carries no information "
                    "and is NOT reported as empty counters."),
            empty_means=None,
            count=0,
            data={},
            **common,
        )

    counters = {c.tag: (c.text or "").strip() for c in statistics_elem}

    if not counters:
        return section(
            status="unknown_by_design",
            reason=("<statistics> is present but holds no counter elements -- this farm "
                    "has recorded nothing yet. The container is right there and it is "
                    "empty, so nothing is being inferred and no absence licence is owed."),
            empty_means="farm_has_none",
            count=0,
            data={},
            **common,
        )

    return section(
        status="ok",
        reason=None,
        empty_means=None,
        count=len(counters),
        data=counters,
        **common,
    )


def roll_up(sections):
    """Top-level status/reason -- § 6.3.3, rev 4. TOTAL, ORDERED, FIRST MATCH WINS.

        1. ANY section unavailable or partial -> "partial"
        2. EVERY section unknown_by_design    -> "unknown_by_design"
        3. otherwise (>=1 ok, none failed)    -> "ok"

    (Rule 0 -- the script could not run at all -> {"error": ...} + exit 1 -- is
    handled by fail() before any section is built, so it cannot reach here.)

    RULE 1 OUTRANKS RULE 2 DELIBERATELY. A domain that is PARTLY unreadable must
    never report the confident unknown_by_design, because unknown_by_design is a
    positive claim about the farm ("this farm has none of this") while a failed
    section means we do not know. § 6.3.3: the status that claims more never
    wins a tie.

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
    guard existed where none can exist. Note the errata already recorded that
    the TESTS were corrected on this point -- the false claim survived here, in
    the script, which is where a maintainer actually meets it.

    This replaces rev 3's rule, which this script wrote as interpretation (a)
    and which had NO rule 2 -- an all-empty domain reported "ok", losing exactly
    the distinction § 6.4 exists to protect, one level up.
    """
    degraded = sorted(name for name, s in sections.items()
                      if s["status"] in ("unavailable", "partial"))
    if degraded:
        return "partial", "section(s) not fully read: " + "; ".join(
            "%s (%s): %s" % (n, sections[n]["status"], sections[n]["reason"])
            for n in degraded)

    # `sections and` guards the vacuous case: all() over an empty dict is True,
    # which would turn a domain that emitted NO sections into the confident
    # claim "this farm has none". A domain with no sections is a bug (§ 6.4),
    # never a positive fact. This template is copied per domain, so the guard
    # is written here rather than left to each builder to rediscover.
    if sections and all(s["status"] == "unknown_by_design" for s in sections.values()):
        return ("unknown_by_design",
                "no data of any kind on this farm for this domain")

    return "ok", None


def main():
    savegame_dir = arg_or_exit("read_farm_ledger.py <savegame_dir> [--farm-id N]")
    farm_id, arg_err = parse_farm_id_arg(sys.argv)
    if arg_err:
        fail(arg_err, False)

    farms_path = os.path.join(savegame_dir, "farms.xml")
    farms_root, farms_generic = load_xml(farms_path)
    if farms_root is None:
        fail(f"could not read farms.xml: {farms_generic.get('error')}", True)

    # --- Select the farm by farmId, never by document order ---
    farm_elems = list(farms_root.iter("farm"))

    # .iter() RECURSES. A <farm> nested anywhere inside another <farm> was
    # therefore visited by this loop, and because the loop kept the LAST match
    # it silently won: a nested decoy <farm farmId="1"> overrode the real farm's
    # name and counters with no diagnostic at all. Finding H5.
    nested = [inner for outer in farm_elems
              for inner in outer.iter("farm") if inner is not outer]
    if nested:
        fail(f"farms.xml holds {len(nested)} <farm> element(s) nested inside "
             "another <farm>. This reader assumes a flat farm list, and a "
             "nested element would silently win the selection. Refusing to "
             "guess which one is the real farm.", True)

    farms_seen = []
    malformed_farm_ids = []
    matches = []
    for farm_elem in farm_elems:
        raw_id = farm_elem.attrib.get("farmId")
        if raw_id is None:
            continue
        try:
            fid = int(raw_id)
        except ValueError:
            malformed_farm_ids.append(raw_id)
            continue
        farms_seen.append(fid)
        if fid == farm_id:
            matches.append(farm_elem)

    # A farmId that will not parse is a schema surprise, and every other schema
    # surprise in this file fails loud. This one used to `continue` -- no
    # counter, no partial, no reason -- so a farm carrying data vanished from
    # the available list entirely and a lookup for it answered "not found",
    # presenting DROPPED data as ABSENT data. Finding C3.
    if malformed_farm_ids:
        shown = ", ".join(repr(m) for m in sorted(set(malformed_farm_ids))[:5])
        fail(f"{len(malformed_farm_ids)} <farm> element(s) carry a farmId that "
             f"is not an integer ({shown}). Skipping them in silence would drop "
             "a real farm out of the available list and answer a lookup for it "
             "with 'not found'. Refusing to drop them.", True)

    if not farms_seen:
        fail("farms.xml parsed but contained no <farm farmId=...> elements -- "
             "schema may have changed.", True)

    # The old loop assigned `target` on every match, so duplicates at the same
    # level resolved to "last one wins" -- also finding H5.
    if len(matches) > 1:
        fail(f"farms.xml holds {len(matches)} <farm> elements carrying farmId "
             f"{farm_id}. The reader kept the last and discarded the others in "
             "silence. Refusing to choose between duplicate farms.", True)

    if not matches:
        fail(f"farm_id {farm_id} not found in farms.xml. "
             f"Available farm_ids: {sorted(farms_seen)}", False)

    target = matches[0]

    sections = {
        "finance_ledger": build_finance_ledger(target, farm_id),
        "lifetime_statistics": build_lifetime_statistics(target, farm_id),
    }
    status, reason = roll_up(sections)

    # ⛔ NO `farm_name` HERE, AND THE OMISSION IS THE FIX. This script used to
    # emit a tenth top-level key. § 6.2 declares EXACTLY NINE -- schema_version,
    # domain, set, farm_id, capability_ids, provenance, status, reason, sections
    # -- and `farm_name` occurs ZERO times in spec rev 4 (or in any earlier
    # revision). Both suites already declared those same nine; this script was
    # the sole outlier, so the envelope was non-uniform in exactly the direction
    # a SUBSET conformance test cannot see. That is finding M1 reproduced one
    # level up, inside the fix for M1.
    #
    # DECLARED vs REMOVED, and why removed. Declaring it would oblige EVERY
    # domain script to emit it -- that is what "every domain script emits
    # exactly this envelope" means -- including read_livestock.py, which reads
    # placeables.xml alone. Farm names live in farms.xml, so livestock would
    # have to open a second file, and carry a second provenance source, purely
    # to repeat a display name. The envelope would also then disagree with the
    # spec, which is BMAD's artifact and is not edited from here.
    #
    # Nothing is lost: the farm is identified by `farm_id` at the top level and
    # again in `provenance.farm_id`, and the name is still available from
    # read_economy.py, which is what farm_snapshot.py already consumes.
    emit({
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN,
        "set": SET,
        "farm_id": farm_id,
        "capability_ids": ["b39", "b40"],
        "provenance": build_provenance(farm_id, [file_provenance(farms_path)]),
        "status": status,
        "reason": reason,
        "sections": sections,
    })


if __name__ == "__main__":
    main()
