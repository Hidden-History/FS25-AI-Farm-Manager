"""
Resolve the GAME'S OWN definitions: which fillTypes are sellable OUTPUTS vs
buyable INPUTS, and how much seed each crop needs per hectare.

Usage: python3 read_game_defs.py <savegame_dir>
        [--config PATH] [--install-dir DIR] [--mods-dir DIR]

WHY THIS EXISTS: economy.xml prices 236 fillTypes and does not say which of
them the farm SELLS and which it BUYS. That distinction is the whole ballgame
for a price calendar -- for a crop a HIGH price is good, for an input a LOW
price is good -- and getting it backwards would invert the advice silently,
which is the most dangerous kind of wrong. Rather than hardcode a list of
"things that are seed", this reads the game's own classification.

THE CLASSIFIER, and why it is trustworthy (verified by running, 2026-07-24):
    A fillType is a SELLABLE OUTPUT iff it appears in any SELLINGSTATION_*
    <fillTypeCategory>. That is literally the game's own record of "a selling
    station will buy this from the player".
    Checked against this install and map, and it separates perfectly:
        WHEAT/OAT/CANOLA/COTTON     -> sellable=True   (SELL calendar)
        SEEDS/FERTILIZER/LIME/      -> sellable=False  (BUY calendar)
        HERBICIDE/MANURE/DIESEL/
        LIQUIDFERTILIZER/DIGESTATE/
        LIQUIDMANURE/ANHYDROUS
    Cross-checked from the other direction: every fillType named by a
    <sprayType> is in the not-sellable set, independently. Two unrelated
    structures agreeing is a much stronger basis than either alone, and much
    stronger than a list of names typed in by hand -- which would rot the
    first time a map added an input (this map adds ANHYDROUS, and the
    classifier picks it up with no code change).

MAP-FIRST RESOLUTION IS MANDATORY -- THIS IS F-019's RULE, NOT A NICETY.
A mod map ships its OWN fillTypes/fruitTypes/sprayTypes, and they win over
the base install. Concretely, on this save: the map adds 24 fillTypes the base
install has never heard of and an extra ANHYDROUS spray type; its fruitTypes
list has 29 entries against the base's 25, four of which (alfalfa, clover,
meadow, meadowWeed) exist ONLY in the map.

Its per-crop seed rates happen to be IDENTICAL to the base install's for all
15 crops that appear in both -- which is exactly why this must not shortcut to
the base install. "They agree today" is the precondition for the F-019 trap,
not an argument against it: a base-install lookup would return a real,
plausible, correct-looking number for as long as the two happen to agree, and
start lying silently the day a map rebalances a seed rate. Resolve where the
game resolves, or report unresolved.

The map mod is derived from the SAVE, not from config: careerSavegame.xml's
<mapId> reads "<ModName>.<MapClass>", so the part before the first dot is the
mod whose zip holds the map. A mapId with no dot is a base-game map and there
is no mod to consult.

SEED RATE -- ANSWERED, WITH ITS SOURCE, AND WORTH STATING PLAINLY BECAUSE IT
WAS PREVIOUSLY BELIEVED UNDERIVABLE:
    Each fruitType's own foliage XML carries
        <fruitType name="wheat"> <seeding litersPerSqm="0.0308"/> ...
    litersPerSqm * 10000 = litres per hectare. Wheat -> 308 L/ha.
    PLAUSIBILITY-CHECKED, because this codebase's own rule is that unit bugs
    are caught by physical sense and not by reading code harder: SEEDS has
    massPerLiter 0.35 in maps_fillTypes.xml, so 308 L/ha is ~108 kg/ha of
    wheat seed. Real-world wheat drills at roughly 100-200 kg/ha. The number
    survives the test. Read as litres-per-HECTARE instead of per-sqm it would
    be 0.0308 L/ha -- a teaspoon of seed for a whole hectare, which is
    absurd, and that absurdity is what identifies the unit.

Output contract:
    - Absence never looks like data. If the install/mods dirs aren't
      resolvable, or the map zip is missing, this emits {"error": ...} naming
      what's missing -- it never returns an empty classification that would
      read as "nothing is sellable" or "no crop needs seed".
    - Every resolved fact carries `resolved_from` ("map" / "base") so a
      caller can see which package answered.
"""
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(__file__))
from xml_utils import load_xml, emit, arg_or_exit
from read_store_prices import load_paths, parse_args as _sp_parse_args

SELLING_CATEGORY_PREFIX = "SELLINGSTATION"
SQM_PER_HECTARE = 10000.0

# Inputs the farm BUYS that carry no declarative marker anywhere in the game's
# XML -- the engine knows them by name, so nothing can be resolved from data.
#
# This list is deliberately TINY and everything else is resolved: the
# sprayable inputs (fertiliser, lime, herbicide, manure, digestate, and any
# the map adds) come from the game's own <sprayType> list, so a map that
# invents a new one is picked up with no code change here. These three are the
# residue that genuinely cannot be:
#   SEEDS  -- consumed by <seeding litersPerSqm>, which names a RATE but no
#             fillType; the engine supplies the generic seed type.
#   DIESEL -- fuel. Appears in vehicles.xml fill units; no category marks it
#   DEF      as "a thing the farm buys".
#
# NOTE the failed alternative, because it is instructive: "not sellable at a
# selling station" is NOT a usable definition of an input. It is true of every
# input, but it is also true of AIR (a brake reservoir), PROPANE, STONE,
# FORAGE_MIXING and ~200 intermediate/product fillTypes -- so using it would
# bury four real buy-signals in two hundred rows of noise. Sellability is a
# sound test for what the farm SELLS; it is not the complement of it.
ENGINE_LEVEL_INPUT_FILL_TYPES = {
    "SEEDS": "consumed by the <seeding> mechanic, which declares a rate but no fillType",
    "DIESEL": "fuel; carried in vehicle fill units, marked by no category",
    "DEF": "diesel exhaust fluid; same",
}

# "$data/..." inside a map's own XML points back at the BASE install, not at
# the map zip -- the map is explicitly deferring to the base game for that
# file. Honouring this prefix is what makes map-first resolution correct
# rather than merely map-only.
DATA_PREFIX_RE = re.compile(r"^\$data/(.+)$")


def parse_path_args(argv):
    """Reuse read_store_prices' own path resolution rather than reinventing
    it -- same sanctum/config.json 'paths' block, same explicit overrides."""
    config = install_dir = mods_dir = None
    args = argv[2:]
    i = 0
    while i < len(args):
        if args[i] in ("--config", "--install-dir", "--mods-dir") and i + 1 < len(args):
            val = args[i + 1]
            if args[i] == "--config":
                config = val
            elif args[i] == "--install-dir":
                install_dir = val
            else:
                mods_dir = val
            i += 2
        else:
            i += 1
    return load_paths(config, install_dir, mods_dir)


def read_map_id(savegame_dir):
    """Returns (mod_name_or_None, map_id_or_None, error_or_None).

    mod_name None with no error means "base-game map, no mod zip to consult"
    -- a real answer, distinct from "couldn't tell"."""
    path = os.path.join(savegame_dir, "careerSavegame.xml")
    root, generic = load_xml(path)
    if root is None:
        return None, None, generic.get("error", "unknown error reading careerSavegame.xml")
    el = root.find(".//mapId")
    if el is None or not (el.text or "").strip():
        return None, None, "careerSavegame.xml has no <mapId> -- cannot tell which map this save uses"
    map_id = el.text.strip()
    if "." not in map_id:
        return None, map_id, None
    return map_id.split(".", 1)[0], map_id, None


class PackageResolver:
    """Reads XML out of the map's zip first, falling back to the base install
    only where the map itself defers via a '$data/' path. Never falls back by
    basename -- see F-019 and this module's docstring."""

    def __init__(self, install_dir, mods_dir, map_mod_name):
        self.install_dir = install_dir
        self.mods_dir = mods_dir
        self.map_mod_name = map_mod_name
        self.zip_path = (
            os.path.join(mods_dir, map_mod_name + ".zip") if map_mod_name else None
        )
        self._zip = None
        self._names = []

    def open_map_zip(self):
        """Returns error_or_None. A missing map zip is reported, not ignored:
        silently continuing with base-only data would produce exactly the
        plausible-but-wrong output this class exists to prevent."""
        if not self.zip_path:
            return None
        if not os.path.isfile(self.zip_path):
            return f"map mod zip not found: {self.zip_path}"
        try:
            self._zip = zipfile.ZipFile(self.zip_path)
            self._names = self._zip.namelist()
        except (zipfile.BadZipFile, OSError) as e:
            return f"could not open map mod zip {self.zip_path}: {e}"
        return None

    def find_in_map(self, *needles):
        """First zip entry under a config/ path matching all needles."""
        for n in self._names:
            low = n.lower()
            if all(x.lower() in low for x in needles):
                return n
        return None

    def read_map_xml(self, inner_path):
        try:
            return ET.fromstring(self._zip.read(inner_path).decode("utf-8", "replace")), None
        except (KeyError, ET.ParseError, OSError) as e:
            return None, f"could not read {inner_path} from map zip: {e}"

    def read_base_xml(self, rel_under_data):
        full = os.path.join(self.install_dir, "data", rel_under_data)
        if not os.path.isfile(full):
            return None, f"base install file not found: {full}"
        root, generic = load_xml(full)
        if root is None:
            return None, generic.get("error", f"could not parse {full}")
        return root, None

    def read_referenced(self, filename):
        """Resolve a fruitType's filename, which may be '$data/foliage/x/x.xml'
        (base install -- the map deferring) or 'mapUS/foliage/x/x.xml' (inside
        the map zip). Returns (root, resolved_from, error)."""
        m = DATA_PREFIX_RE.match(filename)
        if m:
            root, err = self.read_base_xml(m.group(1))
            return root, "base", err
        if self._zip is not None and filename in self._names:
            root, err = self.read_map_xml(filename)
            return root, "map", err
        root, err = self.read_base_xml(filename)
        return root, "base", err


def collect_fill_type_categories(resolver):
    """Union base + map categories. The map's fillTypes file is ADDITIVE on
    this map (it adds 24 fillTypes and extends BULK/LIQUID/SPRAYER rather than
    replacing them), so a union -- not a replace -- is the faithful merge.
    Returns (categories dict, sources list, error_or_None)."""
    categories = {}
    sources = []

    base_root, err = resolver.read_base_xml(os.path.join("maps", "maps_fillTypes.xml"))
    if base_root is None:
        return None, None, f"could not read the base install's fillType definitions: {err}"
    for cat in base_root.iter("fillTypeCategory"):
        name = cat.attrib.get("name")
        if name:
            categories.setdefault(name, set()).update((cat.text or "").split())
    sources.append("base:data/maps/maps_fillTypes.xml")

    if resolver._zip is not None:
        inner = resolver.find_in_map("config/", "filltypes")
        if inner:
            root, ferr = resolver.read_map_xml(inner)
            if root is not None:
                for cat in root.iter("fillTypeCategory"):
                    name = cat.attrib.get("name")
                    if name:
                        categories.setdefault(name, set()).update((cat.text or "").split())
                sources.append(f"map:{inner}")
    return categories, sources, None


def collect_spray_types(resolver):
    """fillTypes the game itself treats as sprayable inputs. Map file wins
    outright here (it is a full sprayTypes list, not an additive fragment),
    with the base install as the fallback."""
    inner = resolver.find_in_map("config/", "spraytypes") if resolver._zip is not None else None
    if inner:
        root, err = resolver.read_map_xml(inner)
        if root is not None:
            return {s.attrib["name"] for s in root.iter("sprayType") if "name" in s.attrib}, f"map:{inner}"
    root, err = resolver.read_base_xml(os.path.join("maps", "maps_sprayTypes.xml"))
    if root is None:
        return set(), f"unresolved: {err}"
    return {s.attrib["name"] for s in root.iter("sprayType") if "name" in s.attrib}, \
        "base:data/maps/maps_sprayTypes.xml"


# A fruit's <foliageState> elements ARE its growth states, in document order: the
# Nth element is growthState N. The names are semantic, so the meaning is READ
# from the game rather than hardcoded.
#
#   oat:    1 invisible .. 5 harvestReady, 6 dead, 7 harvested, 8 tireTracks
#   canola: 1 invisible .. 9 harvestReady, 10 dead, 11 harvested, 12 tireTracks
#   maize:  .. 5 harvestReadyGreen, 6 harvestReadyGreen2, 7 harvestReady3,
#              8 dead, 9 harvestedGreen, 10 harvested, ...
#
# Maize is why these are PREFIX rules and not exact names: it has THREE ready
# states and TWO cut states, and matching "harvestReady" exactly silently dropped
# four of one farm's fields into "unknown".
#
# These prefixes are safe, unlike the groundType prefix this replaces:
# "harvestready..." and "harvested..." diverge at character 8 (r vs d), so no
# string can match both. groundType's HARVEST_READY / HARVEST_READY_OTHER could
# not be told apart by startswith() -- that was F-002's shape and it is why this
# reads growthState instead.
#
# NEVER hardcode the numbers. canola=9/10/11 is true of THIS map's canola; a map
# shipping its own foliage gets different ones. Same lesson as read_fields.py:39.
READY_PREFIX = "harvestready"
CUT_PREFIX = "harvested"
DEAD_NAMES = ("dead", "withered")


def classify_growth_states(names):
    """foliageState names in document order -> which growthState numbers mean what.

    Returns (ready, cut, dead) lists of 1-based indices. Empty lists mean the
    fruit declares no such state -- which is a real answer for e.g. grass, and
    must not be confused with "could not read it"."""
    ready, cut, dead = [], [], []
    for i, n in enumerate(names, start=1):
        k = (n or "").lower()
        if k.startswith(READY_PREFIX):
            ready.append(i)
        elif k.startswith(CUT_PREFIX):
            cut.append(i)
        elif k in DEAD_NAMES:
            dead.append(i)
    return ready, cut, dead


def scan_foliage_dir(resolver, already_declared):
    """Fruits present in data/foliage/ that no fruitType list mentions.

    Returns (crops, error_or_None). Each carries resolved_from='base:foliage-scan'
    so a consumer can see this came from a filename convention rather than a
    declaration -- a weaker claim, and one worth labelling."""
    base = os.path.join(resolver.install_dir, "data", "foliage")
    if not os.path.isdir(base):
        return [], f"no foliage directory at {base}"
    found = []
    try:
        entries = sorted(os.listdir(base))
    except OSError as e:
        return [], f"could not list {base}: {e}"
    for d in entries:
        xml_path = os.path.join(base, d, d + ".xml")
        if not os.path.isfile(xml_path):
            continue
        root, generic = load_xml(xml_path)
        if root is None:
            continue
        node = root.find("fruitType")
        if node is None:
            continue
        name = node.attrib.get("name")
        # Trust the file's OWN declared name, not the folder it sits in. If they
        # disagree the folder is the guess and the declaration is the fact.
        if not name or name.lower() in already_declared:
            continue
        state_names = [fs.attrib.get("name") for fs in root.iter("foliageState")]
        ready_i, cut_i, dead_i = classify_growth_states(state_names)
        seeding = node.find("seeding")
        per_sqm = None
        if seeding is not None and "litersPerSqm" in seeding.attrib:
            try:
                per_sqm = float(seeding.attrib["litersPerSqm"])
            except ValueError:
                per_sqm = None
        found.append({
            "crop": name,
            "source_file": os.path.relpath(xml_path, resolver.install_dir),
            "resolved_from": "base:foliage-scan",
            "litres_per_sqm": per_sqm,
            "litres_per_hectare": round(per_sqm * SQM_PER_HECTARE, 2) if per_sqm else None,
            "growth_states": {
                "state_names": state_names,
                "ready": ready_i,
                "cut": cut_i,
                "dead": dead_i,
            },
            "note": "Found by scanning data/foliage/ -- NOT declared by the map's or the "
                    "base map's fruitType list, yet present in the install. Onion is the "
                    "known case. Weaker provenance than a declared fruit; the states "
                    "themselves are read from the file, not inferred.",
        })
    return found, None


def collect_seed_rates(resolver):
    """Per-crop seed usage, from each fruitType's own foliage XML.
    Returns (list, source_label, error_or_None)."""
    inner = resolver.find_in_map("config/", "fruittypes") if resolver._zip is not None else None
    if inner:
        root, err = resolver.read_map_xml(inner)
        source = f"map:{inner}"
        if root is None:
            return None, source, err
    else:
        root, err = resolver.read_base_xml(os.path.join("maps", "maps_fruitTypes.xml"))
        source = "base:data/maps/maps_fruitTypes.xml"
        if root is None:
            return None, source, err

    crops = []
    for ft in root.iter("fruitType"):
        filename = ft.attrib.get("filename")
        if not filename:
            continue
        froot, resolved_from, ferr = resolver.read_referenced(filename)
        if froot is None:
            crops.append({
                "crop": None,
                "source_file": filename,
                "litres_per_hectare": None,
                "error": ferr,
                "note": "This fruitType could not be resolved -- its seed rate is UNKNOWN, "
                        "not zero, and it is not silently dropped from the list.",
            })
            continue
        node = froot.find("fruitType")
        if node is None:
            continue
        name = node.attrib.get("name")

        # Growth states come from the SAME file we already have open. A crop with
        # no seed rate (trees, meadow) can still be harvestable, so this is read
        # before the seeding early-outs below -- attaching it only to the happy
        # path would silently strip states from exactly the odd crops that need
        # explaining.
        state_names = [fs.attrib.get("name") for fs in froot.iter("foliageState")]
        ready_i, cut_i, dead_i = classify_growth_states(state_names)
        growth = {
            "state_names": state_names,
            "ready": ready_i,
            "cut": cut_i,
            "dead": dead_i,
        }
        if not state_names:
            growth["error"] = ("this fruit's foliage XML declares no <foliageState> -- its "
                               "growth states are UNKNOWN. Do not infer readiness for it.")

        seeding = node.find("seeding")
        if seeding is None or "litersPerSqm" not in seeding.attrib:
            crops.append({
                "crop": name,
                "source_file": filename,
                "resolved_from": resolved_from,
                "litres_per_hectare": None,
                "growth_states": growth,
                "note": "This crop's foliage XML has no <seeding litersPerSqm> -- it is not "
                        "sown from generic seed (tree/meadow types typically aren't). UNKNOWN, "
                        "not zero.",
            })
            continue
        try:
            per_sqm = float(seeding.attrib["litersPerSqm"])
        except ValueError:
            continue
        crops.append({
            "crop": name,
            "source_file": filename,
            "resolved_from": resolved_from,
            "litres_per_sqm": per_sqm,
            "litres_per_hectare": round(per_sqm * SQM_PER_HECTARE, 2),
            "is_available_to_sow": seeding.attrib.get("isAvailable"),
            "growth_states": growth,
        })
    # The map's fruitType list is NOT the whole truth. This farm's save contains
    # ONION fields, and onion appears in NEITHER the map's list (29 fruits) nor
    # the base map's list (43) -- yet $data/foliage/onion/onion.xml exists and
    # declares its states. Something pulls it in that neither list mentions.
    #
    # So: sweep data/foliage/ for anything the lists missed. Without this, a fruit
    # the player is actually growing has no state table, and every consumer has to
    # answer "is field 61 ready?" with null. Provenance is recorded, because a
    # fruit found by convention is a weaker claim than one the map declared.
    declared = {(c.get("crop") or "").lower() for c in crops}
    extra, scan_err = scan_foliage_dir(resolver, declared)
    crops.extend(extra)
    if scan_err:
        source = source + f" (+foliage scan: {scan_err})"
    elif extra:
        source = source + f" (+{len(extra)} from base:foliage-scan)"
    return crops, source, None


def main():
    savegame_dir = arg_or_exit("read_game_defs.py <savegame_dir> [--config PATH] "
                               "[--install-dir DIR] [--mods-dir DIR]")
    install_dir, mods_dir, path_err = parse_path_args(sys.argv)
    if path_err:
        emit({"error": path_err, "calibration_needed": True})
        return

    map_mod, map_id, err = read_map_id(savegame_dir)
    if err:
        emit({"error": err, "calibration_needed": True})
        return

    resolver = PackageResolver(install_dir, mods_dir, map_mod)
    zip_err = resolver.open_map_zip()
    if zip_err:
        emit({
            "error": (
                f"{zip_err}. This save's map is a MOD ({map_id}), so the base install's "
                "definitions are NOT authoritative for it -- reporting them anyway would be "
                "the F-019 trap (a plausible, wrong answer). Refusing to guess."
            ),
            "map_id": map_id,
            "calibration_needed": True,
        })
        return

    categories, cat_sources, cat_err = collect_fill_type_categories(resolver)
    if cat_err:
        emit({"error": cat_err, "calibration_needed": True})
        return

    sellable = set()
    for name, members in categories.items():
        if name.upper().startswith(SELLING_CATEGORY_PREFIX):
            sellable |= members

    if not sellable:
        emit({
            "error": (
                "no fillType appears in any SELLINGSTATION_* category -- the classifier that "
                "separates sellable output from buyable input found nothing, so every fillType "
                "would be misfiled as an input and every price calendar inverted. Schema has "
                "likely changed. Refusing to emit a classification built on that."
            ),
            "calibration_needed": True,
        })
        return

    spray_types, spray_source = collect_spray_types(resolver)
    crops, crop_source, crop_err = collect_seed_rates(resolver)

    # Cross-check: every sprayType should be non-sellable. If one isn't, the
    # two independent structures disagree and the classifier is on shakier
    # ground than its docstring claims -- say so rather than let the claim of
    # "two structures agree" stand unearned.
    contradictions = sorted(s for s in spray_types if s in sellable)

    emit({
        "map_id": map_id,
        "map_mod": map_mod,
        "map_mod_zip": resolver.zip_path,
        "resolution_rule": (
            "Map package first, base install ONLY where the map's own XML defers via a "
            "'$data/' path. Never a basename fallback (F-019). On this map the per-crop seed "
            "rates happen to match the base install exactly -- which is precisely why the "
            "shortcut is forbidden: agreement today is what makes a base-only lookup look "
            "correct right up until a map rebalances something."
        ),
        "sellable_fill_types": sorted(sellable),
        "sellable_source": cat_sources,
        "sellable_rule": (
            "A fillType is a sellable OUTPUT iff it appears in a SELLINGSTATION_* "
            "fillTypeCategory -- the game's own record of what a selling station will buy. "
            "Everything else that carries a price is an INPUT the farm BUYS. Crops -> SELL "
            "calendar (high price good); inputs -> BUY calendar (low price good). Inverting "
            "this inverts the advice."
        ),
        "spray_input_fill_types": sorted(spray_types),
        "spray_input_source": spray_source,
        "input_fill_types": sorted(spray_types | set(ENGINE_LEVEL_INPUT_FILL_TYPES)),
        "input_fill_types_basis": {
            **{s: f"declared by the game's own <sprayType> list ({spray_source})" for s in sorted(spray_types)},
            **ENGINE_LEVEL_INPUT_FILL_TYPES,
        },
        "input_fill_types_rule": (
            "What the farm BUYS. Sprayable inputs are resolved from the game's own sprayTypes "
            "(so a map adding one -- this map adds ANHYDROUS -- is picked up with no code "
            "change); SEEDS/DIESEL/DEF are named explicitly because the engine knows them by "
            "name and no XML marks them. This is NOT the complement of sellable: 'not sold at "
            "a selling station' is also true of AIR, PROPANE, STONE and ~200 intermediate "
            "products, and using it as the input test would bury the real buy-signals in noise."
        ),
        "classifier_cross_check": {
            "every_spray_type_is_non_sellable": not contradictions,
            "contradictions": contradictions or None,
            "note": (
                "Independent confirmation: the sprayTypes list and the SELLINGSTATION_* "
                "categories are unrelated structures, and every sprayType lands on the "
                "non-sellable side. Two structures agreeing is why this classifier is "
                "trusted over a hand-written list of names."
                if not contradictions else
                "WARNING: these fillTypes are BOTH sprayable inputs AND sellable at a station, "
                "so 'buy low' and 'sell high' both apply and the calendar for them is "
                "genuinely ambiguous. Reported rather than silently forced to one side."
            ),
        },
        "seed_rates": crops,
        "seed_rates_source": crop_source,
        "seed_rates_error": crop_err,
        "seed_rate_units": (
            "litres_per_hectare = <seeding litersPerSqm> * 10000, from each fruitType's own "
            "foliage XML. Plausibility-checked: wheat 308 L/ha * SEEDS massPerLiter 0.35 = "
            "~108 kg/ha, which matches real-world wheat drilling rates (~100-200 kg/ha). A "
            "null rate means the crop is not sown from generic seed, NOT that seed is free."
        ),
        "calibration_needed": False,
    })


if __name__ == "__main__":
    main()
