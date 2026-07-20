"""
Read placeables.xml -> owned buildings/silos/husbandry/production, and storage
ownership.

Usage: python3 read_placeables.py <savegame_dir> [--farm-id N]
    (run with --help for the full argparse usage; unknown flags are an error,
    not silently ignored)
    --farm-id N   Which farmId to report on (default: 1, the player's usual farm).

CONFIRMED by running against a real save (farmId=1): every top-level
<placeable> element carries ownership directly as a farmId="N" attribute, same
as <vehicle> in vehicles.xml. The previous version of this script had no
ownership concept at all -- it globbed every placeable in the file (28
husbandry-tagged nodes, 29 production-tagged nodes) regardless of owner.

Ownership shape observed on this save. TREAT THE COUNTS AS A SNAPSHOT, NOT AS
CONSTANTS -- they move while the player plays, and a docstring that pins them
rots (this one did: it said "farmId=1 (1) -- just the farmhouse" and was
already false hours later, when the player built two silos):
    - farmId="0"  -- unowned map props (sawmill, cement factory, etc.)
    - farmId="15" -- a farmId that does NOT appear anywhere in farms.xml.
                     Carries almost all the husbandry/production/silo
                     buildings. This is very likely pre-placed, non-player
                     map infrastructure (the map's built-in "working farm"
                     scenery) rather than a real farm -- farms.xml is the
                     authority on real farms and only lists farmId=1. This
                     script does NOT assert what farm 15 "is"; it only
                     reports it as an unrecognized farm id so a briefing
                     doesn't misattribute those buildings to the player.
    - farmId="1"  -- the player's farm. A LOW owned count here is a true,
                     verified result rather than a parser miss; the player
                     simply owns few buildings. Read the live numbers from
                     the output (placeables.owned_count / by_category_owned),
                     never from this paragraph.

STORAGE OWNERSHIP IS SEPARATE FROM PLACEABLE OWNERSHIP. Nested <storage
farmId="..."/> elements exist inside silos, production points, and husbandries,
and their farmId can differ from their parent <placeable>'s farmId -- e.g. the
map's grainElevatorTriggers (farmId="0", public infrastructure) each contain a
<storage farmId="1"/>, meaning the player's own grain sits inside a
map-owned building. So storage ownership is resolved per-<storage> element,
independently of the parent placeable's owner, and reported separately here.

STORAGE FILL DATA: the previous script's `storages_guess: []` looked right and
was reached by a method that could never have worked: its STORAGE_KEYWORDS
(fillType/fillLevel/capacity) matched nothing on ANY <storage> node, so it
would have reported `storages_guess: []` just as confidently on a farm with
full silos, while still claiming calibration_needed: false. That is the
silent-success bug in its purest form -- a check that cannot fail is not a
check. This version reads the fill data structurally (see below) and
distinguishes "empty" from "unreadable".

EMPTY VS UNKNOWN -- AND HOW THE UNKNOWN HALF GOT RESOLVED (2026-07-16)
----------------------------------------------------------------------
`stored_contents` surfaces holdings per fill type. Two structures carry them,
with different epistemics, and the difference is worth keeping:

  - <bunkerSilo> writes fillLevel EXPLICITLY, including an explicit
    fillLevel="0.000000". The game STATES the zero, so "empty" is a verified
    read.
  - <storage> writes NOTHING when empty: a bare `<storage farmId="N"/>`.

That second one was originally reported as an INFERENCE and NOT as a confirmed
zero, on the grounds that no non-empty <storage> had ever been observed on
this save -- so "empty" and "a filled schema we don't recognise" would produce
byte-identical output, and reporting a confident zero would have been
borrowing confidence this parser had not earned.

IT THEN RESOLVED ITSELF, EXACTLY AS PREDICTED, WITHIN THE HOUR. The player
unloaded canola into a silo mid-session and the filled schema appeared:

    stocked:  <storage index="1" farmId="1">
                  <node fillType="CANOLA" fillLevel="46934.054688"/>
              </storage>
    empty:    <storage farmId="0"/>

So the game emits one <node> per stored fill type and omits them entirely when
there is nothing stored. A childless <storage> means EMPTY -- now a verified
read, and the state is reported as "empty_confirmed" rather than hedged.

Two things worth carrying forward from that:
  1. The hedge was right to exist AND right to be removed. It was removed by
     an observation, not by anyone deciding the guess had aged into a fact.
     That is the only way one of these should ever be retired.
  2. This parser caught the new schema WITHOUT being taught it, because
     extract_fill_entries matches on the fillLevel ATTRIBUTE rather than on an
     assumed tag name. Nothing here knew a <node> tag existed -- the same save
     spells the same idea three ways (<bunkerSilo fillLevel>, <husbandryMeadow>
     <fillType name= fillLevel=>, <storage><node fillType= fillLevel=>), and a
     tag-name matcher would have found some and silently missed the rest. Match
     the data, not the name you expect it to have.

Output contract:
    - Never returns [] / a guess for missing data. If placeables.xml is
      missing or unparsable, or no placeable in the file has a farmId
      attribute at all, this emits {"error": ...} naming what's missing.
    - Reports both the owned set (primary) and total seen (context), for
      placeables AND for storage nodes separately.
    - calibration_needed means "could not confidently locate the structure",
      not "owned count came out low/zero".
    - ENVELOPE (F-119): every exit point — success and each error path — emits
      `calibration_needed` as an explicit bool. It is True ONLY for schema
      surprises (the file parsed but the expected structure is absent); input
      and usage errors (bad args, missing/unreadable file, a farm_id not in
      the file) say False, because nothing about the parser's structural
      assumptions is in doubt on those paths. Error paths also carry the
      context known by that point (file, farm_id, ...).
"""
import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit


class ToolkitArgumentParser(argparse.ArgumentParser):
    """Failures keep the toolkit's machine contract (structured JSON on
    stdout, exit 1) instead of argparse's usage-to-stderr + exit 2; --help
    stays argparse-native (stdout, exit 0). Same pattern as
    read_farmland_areas.py -- duplicated, not imported, per this toolkit's
    no-cross-script-imports convention."""

    def error(self, message):
        emit({
            "error": f"{message} ({self.format_usage().strip()})",
            "calibration_needed": False,
        })
        sys.exit(1)


def parse_args(argv):
    parser = ToolkitArgumentParser(
        prog="read_placeables.py",
        description="Read placeables.xml: owned buildings/silos/husbandry/"
                    "production, and storage ownership and contents.",
    )
    parser.add_argument("savegame_dir", help="the savegame directory to read")
    parser.add_argument("--farm-id", type=int, default=1, metavar="N",
                        help="which farmId to report on (default: 1, the "
                             "player's usual farm)")
    return parser.parse_args(argv[1:])


def emit_error(msg, *, calibration_needed, **context):
    """The single door for every error exit, so all of them share one
    envelope: error + calibration_needed (explicit bool, semantics per the
    Output contract above) + whatever context is known by that point."""
    out = {"error": msg}
    out.update(context)
    out["calibration_needed"] = calibration_needed
    emit(out)

# Child tags that indicate what kind of thing a placeable is, in priority
# order (a placeable can have several; the first match wins as primary_type).
# Tags NOT in this list (customImage, animatedObjects, wardrobe, configuration,
# newFence) are auxiliary/decorative and never used as the primary type.
TYPE_TAGS = [
    "husbandry", "husbandryMeadow", "productionPoint", "silo", "bunkerSilo",
    "farmhouse", "sellingStation", "windTurbine", "beehivePalletSpawner",
    "trainSystem", "constructible",
]


def classify(placeable_elem):
    child_tags = [c.tag for c in list(placeable_elem)]
    primary = next((t for t in TYPE_TAGS if t in child_tags), "other")
    return primary, child_tags


def storage_fill_summary(storage_elem):
    """Report whatever fill-data children/attrs a <storage> node actually has,
    without assuming a schema. Empty dict if truly empty."""
    out = {}
    extra_attrs = {k: v for k, v in storage_elem.attrib.items() if k not in ("farmId", "index")}
    if extra_attrs:
        out["attrs"] = extra_attrs
    children = list(storage_elem)
    if children:
        out["children"] = [{"tag": c.tag, "attrs": dict(c.attrib)} for c in children]
    return out


def extract_fill_entries(elem):
    """Pull (fill_type, litres) pairs out of an element and its descendants,
    schema-agnostically -- FS25 writes fill data as either a fillType/name
    attribute pair on the element itself or on child elements, and this save
    contains both spellings (bunkerSilo carries fillLevel directly;
    husbandryMeadow uses <fillType name=... fillLevel=.../>). Matching on the
    ATTRIBUTES rather than on an assumed tag name is what makes this robust to
    the spelling difference.

    Returns a list of {fill_type, fill_level_litres, source_tag}. An empty
    list means "no fill entries found", which the CALLER must interpret --
    it is not this function's job to decide whether that means empty or
    unknown, because the answer differs by node type (see storage_contents
    and bunker_silo_contents below).
    """
    entries = []
    for node in elem.iter():
        attrs = node.attrib
        if "fillLevel" not in attrs:
            continue
        fill_type = attrs.get("fillType") or attrs.get("name")
        try:
            level = float(attrs["fillLevel"])
        except ValueError:
            level = None
        entries.append({
            "fill_type": fill_type,
            "fill_level_litres": level,
            "source_tag": node.tag,
            "level_note": None if level is not None else
                          f"fillLevel={attrs['fillLevel']!r} is unparsable -- level UNKNOWN, not 0.",
        })
    return entries


def storage_contents(storage_elem):
    """What's in a <storage> node -- and how confident we are that that's the
    whole truth.

    THIS IS THE EMPTY-VS-UNKNOWN CRUX, and it does NOT resolve as cleanly as
    "the silos are empty". Read carefully before quoting a number from it.

    In this save, all 53 <storage> nodes are literally `<storage farmId="N"/>`
    -- no children, no fill attributes, nothing. That is CONSISTENT with the
    silos being empty (the farm has 0 hectares ever worked and has sold
    nothing), and FS games conventionally omit zero-valued fill types rather
    than writing them out. But it is not PROOF: no non-empty <storage> node
    has ever been observed in this save, so the filled schema is unverified,
    and "the game writes nothing when empty" and "the game writes something we
    don't recognise" produce identical bytes here.

    Contrast <bunkerSilo>, which in this same file writes an EXPLICIT
    fillLevel="0.000000". That is a verified zero -- the game stated it. The
    difference between a stated zero and a silence is the entire distinction
    this codebase exists to preserve, so the two are reported with different
    `state` values and are never merged into one "empty" count.
    """
    entries = extract_fill_entries(storage_elem)
    if entries:
        return {
            "state": "has_contents",
            "entries": entries,
            "note": "Fill entries read directly from this <storage> node's <node> children.",
        }
    return {
        "state": "empty_confirmed",
        "entries": [],
        "note": (
            "EMPTY, and this is now a verified read rather than an inference. The filled "
            "schema has been OBSERVED on this save (2026-07-16): a stocked store writes "
            "'<storage index=\"1\" farmId=\"1\"><node fillType=\"CANOLA\" fillLevel=\"46934.05\"/>"
            "</storage>', while an empty one writes '<storage farmId=\"0\"/>' -- no children at "
            "all. So the game demonstrably emits a <node> per stored fill type and omits them "
            "entirely when there is nothing stored. A childless <storage> therefore means "
            "empty. This was previously reported as an INFERENCE, correctly, because no "
            "non-empty <storage> had ever been seen here; the player stored grain and it "
            "resolved exactly as predicted."
        ),
    }


def bunker_silo_contents(placeable_elem):
    """<bunkerSilo> writes fillLevel explicitly, including an explicit zero --
    so unlike <storage>, this IS a verified reading either way. Returns None
    when the placeable has no bunkerSilo child at all (i.e. not applicable),
    which is distinct from a bunker silo that is verifiably empty."""
    bunker = placeable_elem.find("bunkerSilo")
    if bunker is None:
        return None
    entries = extract_fill_entries(bunker)
    total = sum(e["fill_level_litres"] or 0.0 for e in entries)
    return {
        "state": "has_contents" if total > 0 else "empty_confirmed",
        "entries": entries,
        "fermenting_time": bunker.attrib.get("fermentingTime"),
        "note": (
            "<bunkerSilo> writes fillLevel explicitly -- this save shows fillLevel=\"0.000000\", "
            "a zero the game actually STATED. That makes 'empty' a verified read here, unlike "
            "a bare <storage> node whose emptiness is only inferred from silence."
        ),
    }


def main():
    ns = parse_args(sys.argv)
    savegame_dir, farm_id = ns.savegame_dir, ns.farm_id

    path = os.path.join(savegame_dir, "placeables.xml")
    root, generic = load_xml(path)

    if root is None:
        emit_error(generic.get("error", "unknown error reading placeables.xml"),
                   calibration_needed=False, file=path, farm_id=farm_id)
        return

    all_placeables = list(root.iter("placeable"))
    if not all_placeables:
        emit_error(
            "placeables.xml parsed but contained no <placeable> elements -- schema may have changed.",
            calibration_needed=True, file=path, farm_id=farm_id,
        )
        return

    missing_farm_id = [p for p in all_placeables if "farmId" not in p.attrib]
    if len(missing_farm_id) == len(all_placeables):
        emit_error(
            "no <placeable> element in placeables.xml has a farmId attribute -- schema may have changed. Cannot determine ownership.",
            calibration_needed=True, file=path, farm_id=farm_id,
            total_seen=len(all_placeables),
        )
        return

    seen_farm_ids = set()
    owned = []
    by_category_total = {}
    by_category_owned = {}

    # Storage bookkeeping: walk each placeable's descendant <storage> nodes so
    # we can report which parent placeable each one belongs to.
    all_storage_nodes = []
    storage_seen_farm_ids = set()
    owned_storage_nodes = []
    owned_bunker_silos = []

    for p in all_placeables:
        a = p.attrib
        primary, child_tags = classify(p)
        by_category_total[primary] = by_category_total.get(primary, 0) + 1

        fid = None
        if "farmId" in a:
            try:
                fid = int(a["farmId"])
                seen_farm_ids.add(fid)
            except ValueError:
                pass

        if fid == farm_id:
            by_category_owned[primary] = by_category_owned.get(primary, 0) + 1
            owned.append({
                "unique_id": a.get("uniqueId"),
                "filename": a.get("filename"),
                "mod_name": a.get("modName"),
                "price": float(a["price"]) if a.get("price") is not None else None,
                "primary_type": primary,
                "child_tags": child_tags,
            })

        for s in p.iter("storage"):
            all_storage_nodes.append(s)
            s_fid = s.attrib.get("farmId")
            if s_fid is None:
                continue
            try:
                s_fid_int = int(s_fid)
            except ValueError:
                continue
            storage_seen_farm_ids.add(s_fid_int)
            if s_fid_int == farm_id:
                owned_storage_nodes.append({
                    "parent_placeable_unique_id": a.get("uniqueId"),
                    "parent_placeable_filename": a.get("filename"),
                    "parent_placeable_farm_id": fid,
                    "storage_index": s.attrib.get("index"),
                    "fill_data": storage_fill_summary(s),
                    "contents": storage_contents(s),
                })

        # bunkerSilo contents hang off the placeable itself, not off a
        # <storage> node -- a different structure with different (better)
        # epistemics, so it is collected separately rather than folded in.
        if fid == farm_id:
            bunker = bunker_silo_contents(p)
            if bunker is not None:
                owned_bunker_silos.append({
                    "unique_id": a.get("uniqueId"),
                    "filename": a.get("filename"),
                    "contents": bunker,
                })

    if farm_id not in seen_farm_ids:
        emit_error(
            (
                f"farm_id {farm_id} owns no placeables AND does not appear as a farmId "
                f"on any <placeable> in placeables.xml. Farm ids present in this file: "
                f"{sorted(seen_farm_ids)}. Verify this --farm-id against farms.xml before "
                f"trusting a '0 owned' result."
            ),
            calibration_needed=False, file=path, farm_id=farm_id,
            farm_ids_seen=sorted(seen_farm_ids),
            total_seen=len(all_placeables),
        )
        return

    any_storage_has_fill_data = any(storage_fill_summary(s) for s in all_storage_nodes)

    # The farm's stored holdings, totalled per fill type across everything that
    # actually reports a level. Only genuinely-read levels land here; a node
    # whose contents are merely INFERRED empty contributes nothing and is
    # counted in stored_contents_unverified_node_count instead, so an
    # inference can never masquerade as a measurement.
    stored_by_fill_type = {}
    for node in owned_storage_nodes:
        for e in node["contents"]["entries"]:
            if not e.get("fill_level_litres"):
                continue
            entry = stored_by_fill_type.setdefault(e["fill_type"], {"total_litres": 0.0, "locations": []})
            entry["total_litres"] += e["fill_level_litres"]
            entry["locations"].append({
                "where": node["parent_placeable_filename"],
                "storage_index": node["storage_index"],
                "litres": e["fill_level_litres"],
            })
    for b in owned_bunker_silos:
        for e in b["contents"]["entries"]:
            if not e.get("fill_level_litres"):
                continue
            entry = stored_by_fill_type.setdefault(e["fill_type"] or "UNSPECIFIED", {"total_litres": 0.0, "locations": []})
            entry["total_litres"] += e["fill_level_litres"]
            entry["locations"].append({
                "where": b["filename"],
                "storage_index": None,
                "litres": e["fill_level_litres"],
            })

    confirmed_empty = [n for n in owned_storage_nodes
                       if n["contents"]["state"] == "empty_confirmed"]

    emit({
        "file": path,
        "farm_id": farm_id,
        "placeables": {
            "owned_count": len(owned),
            "total_seen": len(all_placeables),
            "farm_ids_seen": sorted(seen_farm_ids),
            "by_category_owned": by_category_owned,
            "by_category_total": by_category_total,
            "owned": owned,
        },
        "stored_contents": {
            "by_fill_type": stored_by_fill_type,
            "fill_types_stored": sorted(stored_by_fill_type),
            "state": "holding" if stored_by_fill_type else "nothing_read_as_stored",
            "storage_nodes_empty_confirmed_count": len(confirmed_empty),
            "bunker_silos_owned_count": len(owned_bunker_silos),
            "bunker_silos_empty_confirmed_count": sum(
                1 for b in owned_bunker_silos if b["contents"]["state"] == "empty_confirmed"
            ),
            "note": (
                "Litres actually READ from a stated level. Value them with read_fill_prices.py "
                "(economy.xml's per-period curve) -- never read_prices.py's meanValue, which is "
                "0 on this never-traded farm and would price stored grain at nothing."
                if stored_by_fill_type else
                "The farm stores nothing -- and this is a CHECKED result, not a silence. Both "
                "storage structures state their emptiness verifiably: <bunkerSilo> writes an "
                "explicit fillLevel=0, and a <storage> node writes a <node fillType= fillLevel=> "
                "child per stored fill type and omits it entirely when empty (that filled schema "
                "was directly observed on this save on 2026-07-16, which is what turned 'empty' "
                "here from an inference into a read). A childless <storage> therefore means "
                "empty, not unreadable."
            ),
        },
        "storage_nodes": {
            "owned_count": len(owned_storage_nodes),
            "total_seen": len(all_storage_nodes),
            "farm_ids_seen": sorted(storage_seen_farm_ids),
            "owned": owned_storage_nodes,
            "any_fill_data_found": any_storage_has_fill_data,
            "note": (
                "storage ownership (farmId on <storage>) can differ from the parent "
                "<placeable>'s farmId -- e.g. player-owned grain sitting in a map-owned "
                "grain elevator trigger. Reported independently of placeable ownership above. "
                "any_fill_data_found reflects whether any <storage> node carries fill data. "
                "The filled schema is known and observed (<node fillType= fillLevel=/> children); "
                "an empty store writes no children at all. So false here means EMPTY, verifiably, "
                "not 'unreadable' -- see stored_contents.note."
            ),
        },
        "bunker_silos": {
            "owned_count": len(owned_bunker_silos),
            "owned": owned_bunker_silos,
            "note": (
                "<bunkerSilo> hangs off the placeable, not off a <storage> node, and writes "
                "fillLevel EXPLICITLY -- including an explicit 0.000000. A zero here is a "
                "verified read, not an inference from silence. This is the structure a plain "
                "<storage> node can be compared against to see why its silence is weaker "
                "evidence."
            ),
        },
        "unrecognized_farm_ids": sorted(fid for fid in seen_farm_ids if fid != 0 and fid != farm_id),
        "unrecognized_farm_ids_note": (
            "farmIds seen on placeables that are neither 0 (map-unowned) nor the "
            "requested --farm-id. These do not appear in farms.xml as real farms. "
            "Likely pre-placed non-player map infrastructure; not verified further, "
            "and NOT counted as owned by any player farm."
        ),
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
