"""
DOMAIN SCRIPT (weather set) -- environment and forecast, in the sec. 6.2 envelope.

Usage: python3 read_weather.py <savegame_dir> [--farm-id N]
                               [--config PATH] [--install-dir DIR] [--mods-dir DIR]

Built against architecture-farm-manager-cached-state.md rev 4. Follows
read_livestock.py, which is the ratified template: the sec. 6.2 envelope with
sec. 6.3.1's absence rule, sec. 6.3.3's roll-up and sec. 6.5's typing rule.

Capabilities, from the capability inventory's bucket (b) sec. 2.5 "Weather":

    b29  full 30-instance forecast   -- environment.xml (SAVE)
    b30  hail / twister events       -- environment.xml (SAVE)
    b31  ground wetness / snow       -- environment.xml (SAVE)
    b27  weather-type probability weights -- mapUS/config/environment.xml (MAP-MOD)
    b28  rain intensity presets           -- mapUS/config/environment.xml (MAP-MOD)
    b26  temperature per forecast slot    -- MAP-MOD join SAVE

b23 and b25 are NOT here and are not this domain's: they read vehicles.xml and
belong to wave 2's `read_bales_pallets.py`. Recorded so a reader does not go
looking for the fleet's 22 pallets in the weather set.

Reads read-only: the savegame's environment.xml, and -- when the map paths
resolve -- the map mod's config/environment.xml from inside its zip. Nothing
here writes to the savegame, ever. The only writes this process performs are to
stdout.

WEATHER IS MAP-WIDE, NOT FARM-SCOPED
------------------------------------
collect_state.py's own note says it: "weather is weather". No element read here
carries a farmId and nothing is filtered by one. `--farm-id` is accepted and
echoed for sec. 6.2 envelope conformance -- it records WHICH FARM THIS REPORT IS
FOR, and it is NOT a filter. Do not read a farm_id in this envelope as evidence
that the figures were scoped; they were not, and they are the same for every
farm on the map.

⛔ THIS DOMAIN COERCES NOTHING, AND THAT IS A MEASUREMENT
--------------------------------------------------------
sec. 6.5 rule 1: the default is `raw`, and rule 2 requires a resolvable schema
citation before any coercion. THERE IS NO SCHEMA TO CITE. Measured with two
differently-shaped probes over all 88 XSDs in the game install's
shared/xml/schema/ (2026-08-02):

  Probe A -- element:   grep -l '<xs:element name="environment"' *.xsd
                        -> only mission00.xsd, which declares a MAP-definition
                           <environment>, not the savegame's.
  Probe B -- attribute: grep -lE 'name="(currentMonotonicDay|timeSinceLastRain|
                        daysPerPeriod)"' *.xsd  ->  NO FILES.

There is no savegame_environment.xsd; environment.xml has no savegame schema at
all. The map-mod side is no better: NO xsd anywhere declares minTemperature,
maxTemperature or rainfallScale. So every field this domain emits ships raw,
exactly as sec. 7.2's b40 does for the same reason -- "no schema guarantee of
lossless numeric coercion exists, so DEC-047's default applies: raw."

Two probes rather than one because they are structurally independent: one asks
"is the element declared", the other "is the attribute declared". A single grep
returning nothing is a statement about a spelling, not about the schema set.

Raw also protects real data here. `wetness="0.000000"` and `height="0.000000"`
are FIXED-PRECISION ZEROS (sec. 6.5's hazard table): 0.0 is a value, not
absence, and the string keeps that distinction visible where a coerced 0 would
blur it against a missing attribute.

b26 IS A RULED READING, AND IT SHIPS THE EVIDENCE THAT WOULD EXPOSE IT WRONG
---------------------------------------------------------------------------
b26 needs a join: the savegame slot carries season + typeName + variationIndex,
the map mod carries the temperatures. Both halves are present and readable --
this script reads the map half for b27 and b28 regardless. What is undocumented
is the SEMANTICS of variationIndex, so the reading is RULED and labelled as one
(TEMPERATURE_RULING, carried in the section's `reason`).

Two claims, and they have different standing -- collapsing them is how a ruling
gets laundered into a fact:

  1. THE INDEX IS 1-BASED. Measured, and 0-based is FALSIFIED rather than merely
     disfavoured: over all 30 instances, 0 are out of range under 1-based and 6
     are out of range under 0-based -- reads past the end of an array the game
     itself wrote -- while max_index_seen equals the object's variation count for
     4 of the 5 (season, typeName) keys present.
  2. THE JOIN ITSELF is ASSERTED, not derived. That (season, typeName,
     variationIndex) addresses that object's variation list at all comes from the
     capability inventory (b26), not from documentation. Five differently-phrased
     fs25-lookup searches at corpus 86f08357778f found no page describing weather
     variation selection; "forecast" is absent from the entire 1,661-page index;
     no WeatherManager or WeatherObject page exists -- the token "WeatherObject"
     decomposes to weather+object and lands on NightlightFlicker, SunAdmirer and
     Placeable, none of which bear on it.

⚠ NO GUARD HERE CAN CATCH A WRONG JOIN. An out-of-range index is caught and
reported as falsifying the 1-based reading, but a wrong join with in-range
indices produces a plausible temperature and fires nothing.

That is why every row ships its raw variationIndex AND its variation_candidates
count beside the temperature. A bare temperature is unfalsifiable; "index 4 of 4
candidates" is checkable by a reader who does not trust the join. This project's
top harm is a confident wrong number, and the cheapest defence is shipping the
number together with the thing that would reveal it wrong.

⛔ WHY THE LABEL LIVES IN `reason`. sec. 6.2 has `absence_guarantee.kind:
"design_ruling"` for a ruled ABSENCE and NO field at all for a ruled
INTERPRETATION. So a ruled reading has nowhere structured to live and ends up as
prose. That is a recorded spec gap, filed as a spec item -- not a shortcut taken
here.

WHAT THIS SCRIPT DOES NOT RESTATE
---------------------------------
read_environment.py already emits current_weather, clock, season, current_day,
days_per_period and time_since_last_rain, and it is not this lane's file to
change. Under DEC-048 (1) the authored half may reference a generated value and
never repeat it, so none of those are re-emitted here. This domain adds only
what nothing gathers: the 25 forecast instances read_environment.py discards,
the severe-weather events nested inside them, the ground/snow state, and the two
map-mod tables.

Output contract:
    - Could-not-run -- bad args, unreadable environment.xml -- emits a
      top-level {"error": ...} and exits 1 (sec. 6.3, DEC-001). Never [], never
      {}, never None, never a coerced guess.
    - The script ran -- the envelope is emitted with all five sections always
      present. A section is never suppressed, on any save, ever. A map-mod
      section whose paths do not resolve reports `unavailable` IN BAND, naming
      the fix; it never silently disappears and never reports an empty table.
"""
import hashlib
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit
from read_store_prices import load_paths
from read_game_defs import read_map_id, PackageResolver

SCHEMA_VERSION = 1
GENERATOR = "read_weather.py"
GENERATOR_VERSION = "1.0.0"
USAGE = ("read_weather.py <savegame_dir> [--farm-id N] "
         "[--config PATH] [--install-dir DIR] [--mods-dir DIR]")

DOMAIN = "weather"
SET = "weather"
CAPABILITY_IDS = ["b26", "b27", "b28", "b29", "b30", "b31"]

# sec. 6.5 rules 1-2, and this is the whole typing story for this domain: no
# schema exists to cite, so nothing is coerced. See the module docstring for the
# two probes that establish it. Stated once here and referenced by every
# section, because five copies of one sentence is five things to keep in sync
# (DEC-048 (1), applied to this file's own constants).
NO_SCHEMA_GUARANTEE = (
    "RAW BY MEASUREMENT, not by preference. environment.xml has NO savegame "
    "schema: across all 88 XSDs in shared/xml/schema/, no file declares a "
    "savegame <environment> element (only mission00.xsd's map-definition one) "
    "and no file declares currentMonotonicDay/timeSinceLastRain/daysPerPeriod. "
    "sec. 6.5 rule 2 requires a resolvable citation before any coercion and "
    "there is none, so DEC-047's default applies: raw. Fixed-precision zeros "
    "like wetness=\"0.000000\" additionally MUST stay raw -- 0.0 is a value, "
    "not absence (sec. 6.5 hazard table)."
)

NO_SCHEMA_GUARANTEE_MAP = (
    "RAW BY MEASUREMENT. The map's config/environment.xml has no schema "
    "either: no XSD in shared/xml/schema/ declares minTemperature, "
    "maxTemperature or rainfallScale. sec. 6.5 rule 2 therefore licenses no "
    "coercion and DEC-047's default applies: raw."
)

# The six attributes every <instance> carries. All six are required: a missing
# one is a schema surprise, not a default (sec. 6.5 rule 3's sibling -- absence
# is never filled in).
INSTANCE_ATTRS = ("typeName", "season", "variationIndex",
                  "startDay", "startDayTime", "duration")

# A forecast slot is identified by WHEN IT STARTS. sec. 6.5 rule 5's exception:
# an identity field stays raw however well-typed the schema is -- and here there
# is no schema anyway, so raw is doubly correct. These are source attributes,
# not invented keys: nothing is fabricated to key on.
FORECAST_IDENTITY = ["startDay", "startDayTime"]

# The two severe-event children, and the attributes each declares. Read from the
# live save and from read_environment.py's own confirmed-structure docstring;
# both agree.
EVENT_ATTRS = {
    "hail": ("perlinPercentage",),
    "twister": ("startPosX", "startPosZ", "meterPerHour"),
}

# Element-level, never file-level (sec. 6.2). environment.xml feeds five
# sections and blocking or attributing at file granularity would smear them
# together -- the same distinction that keeps b40 out of BUG-014's net.
SRC_FORECAST = ["environment.xml:environment/weather/forecast/instance"]
SRC_EVENTS = [
    "environment.xml:environment/weather/forecast/instance/hail",
    "environment.xml:environment/weather/forecast/instance/twister",
]
SRC_GROUND = [
    "environment.xml:environment/weather/ground",
    "environment.xml:environment/weather/snow",
    "environment.xml:environment/snow",
]
SRC_WEIGHTS = ["map:mapUS/config/environment.xml:environment/weather/season/object"]
# b26 reads BOTH halves of the join and declares both. A section that declared
# only the map side would understate what it read, and source_elements is the
# trust root of the sec. 6.8 tooth-1 guard -- understating it is how a block gets
# skipped.
SRC_TEMPERATURE = [
    "environment.xml:environment/weather/forecast/instance",
    "map:mapUS/config/environment.xml:environment/weather/season/object/variation",
]
SRC_PRESETS = [
    "map:mapUS/config/environment.xml:environment/weather/rain/presets/preset",
    "map:mapUS/config/environment.xml:environment/weather/rain/types/type",
]


def present_attrs(elem, names):
    """{name: value} for the attributes ACTUALLY PRESENT on elem. Absent ones are
    OMITTED, never emitted as null.

    ⛔ THIS IS THE DEC-001 RULE APPLIED TO ATTRIBUTES, and it was a real defect
    here rather than a precaution. Four sites in this domain built rows with a
    bare `elem.attrib.get(name)`, which emits `null` for an absent attribute --
    and a null in a data row is indistinguishable from a legitimately empty
    value. `{"rainfallScale": null}` reads as "this preset has no rainfall
    scale"; the truth was "the attribute was not there and nobody looked".

    An OMITTED key cannot be misread that way: the consumer either finds the
    field or does not, and there is no third state pretending to be data. This
    is the same rule read_fleet.py applies to <configuration>'s two optional
    attributes, and it is stated once here rather than re-derived per call site.

    Where an attribute is REQUIRED -- the six on <instance> -- this helper is not
    used; those fail loud instead, because a missing one is a schema surprise
    rather than an absent optional value.
    """
    return {name: elem.attrib[name] for name in names if name in elem.attrib}


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
    """Pull --farm-id / --config / --install-dir / --mods-dir out of argv.

    Returns (farm_id, config, install_dir, mods_dir, error_or_None).

    NOTHING IS SWALLOWED. read_livestock.py's parser used to drop every
    argument it did not recognise, so `--farm-id=15` selected farm 1 and exited
    0 -- a confidently reported wrong farm. An unrecognised argument is an error
    here for the same reason: a caller who misspells a flag is told so, and is
    never handed a default in silence.
    """
    farm_id, config, install_dir, mods_dir = 1, None, None, None
    args = argv[2:]  # argv[0] = script, argv[1] = savegame_dir (already consumed)
    valued = {"--farm-id", "--config", "--install-dir", "--mods-dir"}
    i = 0
    while i < len(args):
        arg = args[i]
        name, eq, inline = arg.partition("=")
        if name not in valued:
            return None, None, None, None, (
                f"unrecognised argument {arg!r} -- refusing to ignore it and "
                f"report defaults. usage: {USAGE}")
        if eq:
            raw, i = inline, i + 1
        else:
            if i + 1 >= len(args):
                return None, None, None, None, (
                    f"usage: {USAGE} -- {name} given with no value")
            raw, i = args[i + 1], i + 2
        if name == "--farm-id":
            try:
                farm_id = int(raw)
            except ValueError:
                return None, None, None, None, (
                    f"--farm-id must be an integer, got {raw!r}")
        elif name == "--config":
            config = raw
        elif name == "--install-dir":
            install_dir = raw
        else:
            mods_dir = raw
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


def section(status, reason, shape, cap_ids, typing, guarantee, identity,
            empty_means, absence_guarantee, source_elements, count, data):
    """One sec. 6.2 section, with every declared key present.

    ALL THE KEYS, ALWAYS. sec. 6.2: a MISSING key is a build failure, not a
    default, because defaulting is how a guard gets silently skipped. Routing
    every section through one constructor is what makes that structural rather
    than a thing five call sites must each remember.

    `blocked_by` is None for every section in this domain and is NOT a parameter
    -- environment.xml and the map's config/environment.xml carry no element on
    BUG-014's block list. Making it a parameter would invite a caller to pass
    one, and a section that needs it belongs in a domain that reads a blocked
    element.
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


def unavailable(shape, cap_ids, typing, guarantee, identity, source_elements, reason):
    """A section that could not be read. sec. 6.3.1 rule 1: the DEFAULT for an
    absent container is `unavailable` -- absence is not evidence until something
    licenses it, and nothing in this domain licenses any of it, because there is
    no schema here to license anything (see the module docstring).

    count 0 with data None, never data []: an empty list is what a populated
    section that found nothing looks like, and sec. 6.4 requires those two to be
    structurally distinct. This is the DEC-001 rule applied one level in.
    """
    return section(
        status="unavailable", reason=reason, shape=shape, cap_ids=cap_ids,
        typing=typing, guarantee=guarantee, identity=identity,
        empty_means=None, absence_guarantee=None,
        source_elements=source_elements, count=0, data=None)


def read_forecast(weather_elem):
    """b29 -- every <instance>, not the first five. Returns (section, rows).

    read_environment.py emits `upcoming_forecast` capped at 5 and DISCARDS THE
    OTHER 25 (inventory b29). That cap is correct for a briefing and wrong for a
    cache: the whole point of this layer is that the discarded tail is where
    planning lives.

    EVERY <forecast> CONTAINER IS READ, NOT THE FIRST. find() returns the first
    match and drops the rest in silence -- the exact defect that made
    read_livestock.py report a farm owned no animals while a second <clusters>
    sibling held 42 cows. Nothing documents that the engine writes only one
    <forecast>, so reading all of them costs nothing and assumes nothing.
    """
    if weather_elem is None:
        return unavailable(
            "record_list", ["b29"], {"*": "raw"}, {"*": NO_SCHEMA_GUARANTEE},
            FORECAST_IDENTITY, SRC_FORECAST,
            "environment.xml has no <weather> element. The container is absent "
            "and NO schema licenses reading that as 'this map has no forecast' "
            "-- there is no savegame schema for environment.xml at all -- so "
            "sec. 6.3.1 rule 1 applies: unavailable, not unknown_by_design."), []

    containers = weather_elem.findall("forecast")
    if not containers:
        return unavailable(
            "record_list", ["b29"], {"*": "raw"}, {"*": NO_SCHEMA_GUARANTEE},
            FORECAST_IDENTITY, SRC_FORECAST,
            "<weather> is present but carries no <forecast> container. Absent, "
            "not empty, and unlicensed: no schema establishes that the engine "
            "writes <forecast> when it has no instances, so this is "
            "unavailable (sec. 6.3.1 rule 1), never farm_has_none."), []

    rows, bad = [], []
    for container in containers:
        for inst in container.findall("instance"):
            row = {}
            for attr in INSTANCE_ATTRS:
                raw = inst.attrib.get(attr)
                if raw is None:
                    bad.append(attr)
                    break
                row[attr] = raw
            else:
                rows.append(row)

    if bad:
        # A missing attribute is a schema surprise. Emitting null for it would
        # be exactly the absence-as-data mistake DEC-001 exists to prevent, and
        # dropping the row silently would under-report the forecast.
        return None, sorted(set(bad))

    if not rows:
        # The container is RIGHT THERE and holds nothing. sec. 6.3.1 rule 4:
        # nothing is being inferred, so no licence is needed and
        # absence_guarantee stays null.
        return section(
            "unknown_by_design",
            f"{len(containers)} <forecast> container(s) are present and hold no "
            "<instance> rows -- this map has no forecast scheduled. The "
            "container was found, so this is an observation, not an inference.",
            "record_list", ["b29"], {"*": "raw"}, {"*": NO_SCHEMA_GUARANTEE},
            FORECAST_IDENTITY, "farm_has_none", None, SRC_FORECAST,
            0, []), []

    return section(
        "ok", None, "record_list", ["b29"], {"*": "raw"},
        {"*": NO_SCHEMA_GUARANTEE}, FORECAST_IDENTITY, "farm_has_none", None,
        SRC_FORECAST, len(rows), rows), rows


def read_severe_events(forecast_section, weather_elem):
    """b30 -- hail and twister, extracted from the instances b29 already read.

    Its own section rather than a field on b29's rows, because the question it
    answers is 'is anything damaging coming, and how many' -- and a `count` of
    30 forecast slots cannot answer that. NOT a duplication: b29 declares the
    <instance> element, this declares its <hail>/<twister> CHILDREN, and the two
    source_elements lists are disjoint.
    """
    typing = {"*": "raw"}
    guarantee = {"*": NO_SCHEMA_GUARANTEE}
    identity = ["startDay", "startDayTime", "event_type"]

    if forecast_section["status"] != "ok":
        # b29 could not be read, so its children cannot be either. PARTIAL, not
        # unavailable: this is a knock-on, and saying so keeps the reason
        # honest about which read actually failed.
        return section(
            "partial",
            "cannot be read: the parent forecast section is "
            f"'{forecast_section['status']}' -- {forecast_section['reason']}",
            "record_list", ["b30"], typing, guarantee, identity,
            None, None, SRC_EVENTS, 0, None)

    rows = []
    for container in weather_elem.findall("forecast"):
        for inst in container.findall("instance"):
            for tag, attrs in EVENT_ATTRS.items():
                for elem in inst.findall(tag):
                    # The three slot attributes are safe to read directly: b29
                    # ran first and fails loud unless ALL SIX are present on
                    # every instance, so reaching here means they exist. The
                    # coupling is implicit, so it is stated rather than trusted.
                    row = {
                        "startDay": inst.attrib["startDay"],
                        "startDayTime": inst.attrib["startDayTime"],
                        "typeName": inst.attrib["typeName"],
                        "event_type": tag,
                    }
                    # The event's OWN attributes are optional and are omitted
                    # when absent -- never emitted as null. See present_attrs.
                    row.update(present_attrs(elem, attrs))
                    rows.append(row)

    if not rows:
        # Every instance was inspected and none carried an event element. The
        # containers were present and were read -- sec. 6.3.1 rule 4, no licence
        # owed. This is the ordinary shape of a calm forecast, and under sec. 6.4
        # it is a POPULATED section reading farm_has_none, not a gap.
        return section(
            "unknown_by_design",
            f"none of the {forecast_section['count']} forecast instance(s) "
            "carry a <hail> or <twister> child -- no severe weather is "
            "scheduled. Every instance was inspected, so this is an "
            "observation, not an inference.",
            "record_list", ["b30"], typing, guarantee, identity,
            "farm_has_none", None, SRC_EVENTS, 0, [])

    return section(
        "ok", None, "record_list", ["b30"], typing, guarantee, identity,
        "farm_has_none", None, SRC_EVENTS, len(rows), rows)


def read_ground_conditions(root, weather_elem):
    """b31 -- ground wetness, snow height, snow physical height.

    Three separate elements, and a missing one is reported rather than defaulted
    to zero. A defaulted 0.0 here reads as 'the ground is dry' when the truth is
    'we did not find out' -- workability decisions hang off this, and that is
    DEC-001's distinction in its most literal form.

    timeSinceLastRain is deliberately NOT re-emitted: read_environment.py
    already claims it (`time_since_last_rain`), and under DEC-048 (1) the second
    reader references a claimed value rather than restating it.
    """
    typing = {"*": "raw"}
    guarantee = {"*": NO_SCHEMA_GUARANTEE}

    if weather_elem is None:
        return unavailable(
            "record", ["b31"], typing, guarantee, [], SRC_GROUND,
            "environment.xml has no <weather> element, so neither "
            "weather/ground nor weather/snow can be read. Absent and "
            "unlicensed -- sec. 6.3.1 rule 1.")

    # (output_key, parent, tag, attribute). The output key is stated
    # EXPLICITLY rather than composed from label+attr: composing it produced
    # `ground_wetness_wetness` and left the two distinct snow heights spelled
    # inconsistently. These four keys are the section's contract, so they are
    # written down, not derived. Note that weather/snow@height and
    # environment/snow@height are DIFFERENT ELEMENTS and both ship -- collapsing
    # them to one key would silently drop whichever was read second.
    GROUND_SPEC = (
        ("ground_wetness", weather_elem, "ground", "wetness"),
        ("weather_snow_height", weather_elem, "snow", "height"),
        ("snow_physical_height", root, "snow", "physicalHeight"),
        ("snow_height", root, "snow", "height"),
    )

    found, missing = {}, []
    for key, parent, tag, attr in GROUND_SPEC:
        elems = parent.findall(tag)
        if not elems:
            missing.append(f"{key} (<{tag}>)")
            continue
        values = [e.attrib.get(attr) for e in elems]
        if any(v is None for v in values):
            missing.append(f"{key} (<{tag}>/@{attr})")
            continue
        # Every sibling, never the first -- same rule as the forecast.
        found[key] = values[0] if len(values) == 1 else values

    if not found:
        return unavailable(
            "record", ["b31"], typing, guarantee, [], SRC_GROUND,
            "none of weather/ground, weather/snow or environment/snow is "
            "present in environment.xml. Absent and unlicensed -- no schema "
            "establishes these are written, so sec. 6.3.1 rule 1 applies.")

    if missing:
        # PARTIAL is the honest status: some sources read, some did not
        # (sec. 6.3). Reporting `ok` with the found subset would present a
        # partial read as a complete one.
        return section(
            "partial",
            "read " + ", ".join(sorted(found)) + "; could not read " +
            ", ".join(sorted(missing)) + ". Refusing to substitute 0.0 for an "
            "absent wetness or snow height -- a defaulted zero reads as 'the "
            "ground is dry' when the truth is 'we did not find out'.",
            "record", ["b31"], typing, guarantee, [], None, None, SRC_GROUND,
            len(found), found)

    return section(
        "ok", None, "record", ["b31"], typing, guarantee, [], None, None,
        SRC_GROUND, len(found), found)


def _map_unavailable(shape, cap_id, identity, source_elements, reason):
    return unavailable(
        shape, [cap_id], {"*": "raw"}, {"*": NO_SCHEMA_GUARANTEE_MAP},
        identity, source_elements, reason)


def read_map_weather(savegame_dir, config, install_dir, mods_dir):
    """b27 + b28 -- the map's own weather tables.

    Returns (weights_section, presets_section, variation_table, table_reason).

    `variation_table` maps (SEASON_UPPER, typeName) -> the ordered list of that
    object's <variation> attribute dicts, and is what b26 joins the savegame
    forecast against. It is None when the map half could not be read, and
    `table_reason` then carries the same in-band explanation the two sections
    carry -- b26 must not have to re-derive why.

    Both live in the map mod's config/environment.xml, which is inside its zip.
    Path resolution is read_game_defs.py's, unchanged: explicit
    --install-dir/--mods-dir win, else a config.json 'paths' block, default
    sanctum/config.json relative to cwd. No hardcoded path guess -- that mistake
    is FRICTION-LOG.md F-007.

    ⛔ EVERY FAILURE PATH REPORTS `unavailable` WITH THE FIX NAMED, IN BAND.
    None of them returns an empty table. A caller that cannot tell "the map
    declares no rain presets" from "I could not open the map zip" is holding
    exactly the ambiguity DEC-001 exists to destroy, and the second is by far
    the likelier of the two.
    """
    weights_id = ["season", "typeName"]
    presets_id = ["id"]

    def both(reason):
        return (_map_unavailable("keyed_records", "b27", weights_id,
                                 SRC_WEIGHTS, reason),
                _map_unavailable("record_list", "b28", presets_id,
                                 SRC_PRESETS, reason),
                None, reason)

    install_dir, mods_dir, path_err = load_paths(config, install_dir, mods_dir)
    if path_err:
        return both("map paths unresolved: " + path_err)

    mod_name, map_id, map_err = read_map_id(savegame_dir)
    if map_err:
        return both("could not determine which map this save uses: " + map_err)
    if not mod_name:
        # A real answer, distinct from "couldn't tell": the map is base-game, so
        # there is no map mod zip. Its weather config lives in the sealed .gar
        # archives (inventory c4's packaging fact), so this is genuinely not
        # readable rather than merely not looked for.
        return both(
            f"map {map_id!r} is a base-game map with no mod zip. Its weather "
            "config is inside the install's sealed dataS.gar archive, which a "
            "savegame-XML reader cannot open. Not readable, not merely absent.")

    resolver = PackageResolver(install_dir, mods_dir, mod_name)
    zip_err = resolver.open_map_zip()
    if zip_err:
        return both(zip_err)

    inner = resolver.find_in_map("config/", "environment")
    if not inner:
        return both(
            f"map mod {mod_name!r} carries no config/environment.xml entry, so "
            "its weather tables cannot be read.")

    map_root, read_err = resolver.read_map_xml(inner)
    if read_err:
        return both(read_err)

    weather = map_root.find("weather")
    if weather is None:
        return both(f"{inner} has no <weather> element.")

    # --- b27: per-season weather-type weights ------------------------------
    seasons = weather.findall("season")
    weights = {}
    n_objects = 0
    # (SEASON_UPPER, typeName) -> ordered <variation> attribute dicts. Built in
    # the same pass, because b26's join and b27's weights are two readings of
    # ONE element and walking it twice would let them drift apart.
    #
    # The season key is UPPER-CASED: the map writes name="summer" while the
    # savegame forecast writes season="SUMMER". That is a real and silent
    # mismatch -- a case-sensitive join returns zero rows and would look exactly
    # like "this map declares no temperatures".
    variation_table = {}
    for s in seasons:
        name = s.attrib.get("name")
        if name is None:
            continue
        objects = []
        for o in s.findall("object"):
            objects.append(present_attrs(o, ("typeName", "class", "weight")))
            n_objects += 1
            type_name = o.attrib.get("typeName")
            if type_name is not None:
                variation_table[(name.upper(), type_name)] = [
                    present_attrs(v, ("weight", "minHours", "maxHours",
                                      "minTemperature", "maxTemperature"))
                    for v in o.findall("variation")]
        weights[name] = objects

    if not weights:
        weights_section = section(
            "unknown_by_design",
            f"{inner} has a <weather> element carrying no <season> children -- "
            "the map declares no per-season weather weights. The container was "
            "found, so this is an observation, not an inference.",
            "keyed_records", ["b27"], {"*": "raw"},
            {"*": NO_SCHEMA_GUARANTEE_MAP}, weights_id, "farm_has_none", None,
            SRC_WEIGHTS, 0, {})
    else:
        weights_section = section(
            "ok", None, "keyed_records", ["b27"], {"*": "raw"},
            {"*": NO_SCHEMA_GUARANTEE_MAP}, weights_id, "farm_has_none", None,
            SRC_WEIGHTS, n_objects, weights)

    # --- b28: rain intensity presets ---------------------------------------
    rain = weather.find("rain")
    if rain is None:
        presets_section = _map_unavailable(
            "record_list", "b28", presets_id, SRC_PRESETS,
            f"{inner} has a <weather> element with no <rain> child, so no "
            "intensity presets can be read.")
    else:
        rows = []
        # `kind` distinguishes the two element types this section carries; every
        # other field is the source's own attribute, omitted when absent rather
        # than emitted as null (see present_attrs). A <type> row therefore simply
        # has no rainfallScale key -- which is the truth, where the earlier
        # explicit `"rainfallScale": None` asserted a scale that is absent by
        # design and read as data.
        for preset in rain.iter("preset"):
            row = {"kind": "preset"}
            row.update(present_attrs(preset, ("id", "typeId", "rainfallScale")))
            rows.append(row)
        for rtype in rain.iter("type"):
            row = {"kind": "type"}
            row.update(present_attrs(rtype, ("id", "filename")))
            rows.append(row)
        if not rows:
            presets_section = section(
                "unknown_by_design",
                f"{inner} has a <rain> element carrying no <preset> or <type> "
                "children -- the map declares no rain intensities. The "
                "container was found, so this is an observation.",
                "record_list", ["b28"], {"*": "raw"},
                {"*": NO_SCHEMA_GUARANTEE_MAP}, presets_id, "farm_has_none",
                None, SRC_PRESETS, 0, [])
        else:
            presets_section = section(
                "ok", None, "record_list", ["b28"], {"*": "raw"},
                {"*": NO_SCHEMA_GUARANTEE_MAP}, presets_id, "farm_has_none",
                None, SRC_PRESETS, len(rows), rows)

    return weights_section, presets_section, variation_table, None


# sec. 6.5: raw, for the same measured reason as everything else here -- no XSD
# anywhere declares minTemperature, maxTemperature or rainfallScale. The one
# exception is `variation_candidates`, which is NOT a source value at all.
TEMPERATURE_TYPING = {
    "startDay": "raw", "startDayTime": "raw", "typeName": "raw",
    "season": "raw", "variationIndex": "raw",
    "variation_candidates": "int",
    "weight": "raw", "minHours": "raw", "maxHours": "raw",
    "minTemperature": "raw", "maxTemperature": "raw",
}

TEMPERATURE_TYPING_GUARANTEE = {
    "*": NO_SCHEMA_GUARANTEE_MAP,
    "variation_candidates": (
        "NOT A COERCION AND NOT A SOURCE VALUE. This is a cardinality computed "
        "by this script -- how many <variation> children the joined <object> "
        "carries -- so no XSD citation applies and sec. 6.5 rule 2 does not bind "
        "it. It exists so a consumer can audit the selection: 'index 4 of 4 "
        "candidates' is checkable where a bare temperature is not."
    ),
}

TEMPERATURE_IDENTITY = ["startDay", "startDayTime"]

# ⚖ THE RULING, carried as one string so the wording cannot drift between the
# branches that cite it. It lives in `reason` because sec. 6.2 HAS NO FIELD FOR A
# RULED INTERPRETATION -- `absence_guarantee.kind: "design_ruling"` exists only
# for ruled ABSENCE. That gap is filed as a spec item; this is not a shortcut,
# and labelling the ruling is what keeps it from being laundered into a fact.
TEMPERATURE_RULING = (
    "⚖ RULED READING, not a documented fact. variationIndex is treated as "
    "1-BASED into the joined <object>'s <variation> list. Measured over all 30 "
    "forecast instances on the reference save: 0 are out of range under a "
    "1-based reading and 6 are out of range under a 0-based one -- reads past "
    "the end of an array the game itself wrote -- and max_index_seen equals the "
    "object's variation count for 4 of the 5 (season, typeName) keys present. "
    "That FALSIFIES 0-based rather than merely disfavouring it. What remains "
    "asserted rather than derived is THE JOIN ITSELF: that (season, typeName, "
    "variationIndex) addresses that object's variation list at all. The "
    "capability inventory asserts it (b26); no documentation establishes it -- "
    "five differently-phrased fs25-lookup searches at corpus 86f08357778f found "
    "no page describing weather variation selection, 'forecast' is absent from "
    "the entire 1,661-page index, and no WeatherManager/WeatherObject page "
    "exists. No guard here can catch a wrong join, which is why every row ships "
    "its raw variationIndex and its candidate count: a wrong selection is then "
    "visible and checkable instead of silent."
)


def read_forecast_temperature(forecast_section, table, table_reason):
    """b26 -- min/max temperature per forecast slot, by joining the savegame's
    (season, typeName, variationIndex) against the map's variation list.

    THE HIGHEST-VALUE CAPABILITY IN THIS SET, and the one that can most easily
    ship a confident wrong number. Frost and harvest-window decisions hang off
    it. See TEMPERATURE_RULING for what is measured and what is ruled.

    Three degradations, none of them silent:
      * the map half is unreadable        -> unavailable, carrying b27/b28's reason
      * a slot's (season, typeName) does not join -> partial, naming the slots.
        This is REACHABLE, not hypothetical: the reference map declares no RAIN
        object in winter and no HAIL or TWISTER in autumn, so a save whose
        forecast crosses into those seasons will hit it.
      * an index is out of range          -> partial, and the reason says the
        1-based reading is FALSIFIED, because that is exactly what an
        out-of-range index would mean. Reported in band rather than crashing the
        domain, and the slot ships with no temperature rather than a guess.
    """
    if forecast_section["status"] != "ok":
        return section(
            "partial",
            "cannot be read: the parent forecast section is "
            f"'{forecast_section['status']}' -- {forecast_section['reason']}",
            "record_list", ["b26"], TEMPERATURE_TYPING,
            TEMPERATURE_TYPING_GUARANTEE, TEMPERATURE_IDENTITY, None, None,
            SRC_TEMPERATURE, 0, None)

    if table is None:
        return _map_unavailable("record_list", "b26", TEMPERATURE_IDENTITY,
                                SRC_TEMPERATURE,
                                "the map half of the join is unreadable, so no "
                                "temperature can be resolved: " + table_reason)

    rows, unjoinable, out_of_range = [], [], []
    for slot in forecast_section["data"]:
        key = (slot["season"], slot["typeName"])
        candidates = table.get(key)
        if candidates is None:
            unjoinable.append("%s/%s at day %s" % (key[1], key[0], slot["startDay"]))
            continue
        try:
            index = int(slot["variationIndex"])
        except ValueError:
            out_of_range.append("%s (not an integer) at day %s"
                                % (slot["variationIndex"], slot["startDay"]))
            continue
        # 1-BASED -- the ruling. An index outside 1..n is not clamped and not
        # wrapped: it is reported, because it would be evidence the ruling is
        # wrong and silently coercing it would destroy that evidence.
        if not 1 <= index <= len(candidates):
            out_of_range.append("index %d of %d candidates for %s/%s at day %s"
                                % (index, len(candidates), key[1], key[0],
                                   slot["startDay"]))
            continue
        row = {
            "startDay": slot["startDay"],
            "startDayTime": slot["startDayTime"],
            "typeName": slot["typeName"],
            "season": slot["season"],
            # The two audit fields. The raw index and the candidate count are
            # what make the selection falsifiable by a reader who does not
            # trust the join.
            "variationIndex": slot["variationIndex"],
            "variation_candidates": len(candidates),
        }
        row.update(candidates[index - 1])
        rows.append(row)

    degraded = []
    if unjoinable:
        degraded.append(
            "%d slot(s) have no matching (season, typeName) object in the map's "
            "weather table and are omitted rather than guessed: %s"
            % (len(unjoinable), "; ".join(unjoinable[:5])))
    if out_of_range:
        degraded.append(
            "⚠ %d slot(s) carry a variationIndex outside 1..n: %s. UNDER THE "
            "1-BASED READING THIS SHOULD BE IMPOSSIBLE, so it is evidence the "
            "ruling is WRONG and must be escalated, not absorbed. Those slots "
            "ship no temperature."
            % (len(out_of_range), "; ".join(out_of_range[:5])))

    if degraded:
        return section(
            "partial", " | ".join(degraded) + " || " + TEMPERATURE_RULING,
            "record_list", ["b26"], TEMPERATURE_TYPING,
            TEMPERATURE_TYPING_GUARANTEE, TEMPERATURE_IDENTITY, None, None,
            SRC_TEMPERATURE, len(rows), rows)

    if not rows:
        # The forecast is present and empty, so there is nothing to join. Not an
        # inference -- every slot that existed was inspected (there were none).
        return section(
            "unknown_by_design",
            "the forecast holds no instances, so there is no slot to resolve a "
            "temperature for. Every slot was inspected, so this is an "
            "observation, not an inference.",
            "record_list", ["b26"], TEMPERATURE_TYPING,
            TEMPERATURE_TYPING_GUARANTEE, TEMPERATURE_IDENTITY,
            "farm_has_none", None, SRC_TEMPERATURE, 0, [])

    return section(
        "ok", TEMPERATURE_RULING, "record_list", ["b26"], TEMPERATURE_TYPING,
        TEMPERATURE_TYPING_GUARANTEE, TEMPERATURE_IDENTITY, "farm_has_none",
        None, SRC_TEMPERATURE, len(rows), rows)


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
    claim about the world, and a failed section means we do not know.
    sec. 6.3.3 -- the status that claims more never wins a tie.

    ⚠ THE ORDER IS UNOBSERVABLE, and read_livestock.py's docstring records why:
    the two conditions are DISJOINT, so swapping the branches is a semantic
    no-op and no test can catch it. That finding (M9) is inherited here rather
    than re-learned. The honest guard is the exhaustive truth table in the
    suite, whose teeth ARE measured -- deleting rule 1, deleting rule 2, or
    dropping the empty-sections guard each turn it red.
    """
    degraded = sorted(name for name, s in sections.items()
                      if s["status"] in ("unavailable", "partial"))
    if degraded:
        return "partial", "section(s) not fully read: " + "; ".join(
            "%s (%s): %s" % (n, sections[n]["status"], sections[n]["reason"])
            for n in degraded)

    # `sections and` guards the vacuous case: all() over an empty dict is True,
    # which would turn a domain that emitted NO sections into the confident
    # claim "there is none of this". A domain with no sections is a bug
    # (sec. 6.4), never a positive fact.
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
    farm_id, config, install_dir, mods_dir, arg_err = parse_args(sys.argv)
    if arg_err:
        fail(arg_err, calibration_needed=False)

    env_path = os.path.join(savegame_dir, "environment.xml")
    root, generic = load_xml(env_path)
    if root is None:
        fail(
            f"could not read environment.xml: {generic.get('error')}",
            calibration_needed=True,
        )

    provenance = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "farm_id": farm_id,
        "farm_scoped": False,
        "sources": [file_provenance(env_path)],
    }
    provenance["source_set_hash"] = source_set_hash(provenance["sources"])

    weather_elem = root.find("weather")

    forecast_section, _rows = read_forecast(weather_elem)
    if forecast_section is None:
        # read_forecast returned (None, [missing attribute names]).
        fail(
            "<instance> element(s) in environment.xml are missing required "
            f"attribute(s): {', '.join(_rows)}. Every <instance> observed on "
            "this save and in read_environment.py's confirmed structure "
            "carries all six of " + ", ".join(INSTANCE_ATTRS) + ". Refusing to "
            "substitute a default for a missing attribute, and refusing to "
            "drop the row -- either would under-report the forecast.",
            calibration_needed=True,
        )

    weights_section, presets_section, variation_table, table_reason = (
        read_map_weather(savegame_dir, config, install_dir, mods_dir))

    sections = {
        "forecast": forecast_section,
        "forecast_temperature": read_forecast_temperature(
            forecast_section, variation_table, table_reason),
        "severe_events": read_severe_events(forecast_section, weather_elem),
        "ground_conditions": read_ground_conditions(root, weather_elem),
        "weather_type_weights": weights_section,
        "rain_presets": presets_section,
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
